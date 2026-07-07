"""Destiny ECM 서버측 HTTP 직접연동 클라이언트.

Playwright/에이전트 없이 서버 코드에서 `requests` 로 Destiny ECM 을 직접 호출한다.
`ECM-API-SHARE.md`(Destiny ECM 직접 연동 구현 가이드)의 독립 실행 클라이언트를
프로젝트에 이식한 것으로, 범위는 로그인 · 세션 유지 · 폴더/파일 조회 · 다운로드 ·
프로젝트 폴더 자동 탐색까지다. (업로드/폴더생성/DRM 복호화는 범위 밖)

이 모듈은 순수 HTTP 클라이언트이며 Django 모델을 모른다. 워커/점검 파이프라인과의
연결은 `HttpEcmArtifactSource`(artifact_source.py)가 담당한다.

설계 근거: main/docs/34_http_ecm_source_decisions.md, main/docs/33_artifact_source_boundary.md
"""

from __future__ import annotations

import base64
import re
import urllib.parse

try:  # requests 는 requirements-automation.txt 에만 있으므로 import 실패를 허용한다.
    import requests
except Exception:  # pragma: no cover - 자동화 의존성 미설치 환경
    requests = None


TIMEOUT = 60
DOWNLOAD_TIMEOUT = 300
XOR_KEY = "akRngkfl"


class EcmClientError(RuntimeError):
    """ECM HTTP 호출 실패 일반 오류."""


class EcmSessionExpired(EcmClientError):
    """세션 만료/끊김(401 또는 로그인 페이지 리다이렉트)을 알리는 신호."""


def xor_encrypt(plain: str, key: str = XOR_KEY) -> str:
    """로그인 비밀번호 XOR + Base64 인코딩(가이드 §2)."""
    parts = [str(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(plain)]
    return base64.b64encode("z".join(parts).encode()).decode()


class DestinyECM:
    """Destiny ECM 한 서버(base_url) + 한 탐색 시작점(root_oid) 에 대한 세션 클라이언트.

    로그인은 job 단위 1회(open) 하고 job 내 프로젝트가 세션을 재사용한다(결정 2).
    세션 만료가 감지되면 하위 폴더/파일/다운로드 호출이 1회 자동 재로그인 후 재시도한다.
    """

    def __init__(self, base_url: str, root_oid: str, username: str, password: str):
        if requests is None:  # pragma: no cover - 의존성 미설치 방어
            raise EcmClientError(
                "requests 가 설치되어 있지 않습니다. requirements-automation.txt 를 설치하세요."
            )
        self.base_url = (base_url or "").rstrip("/")
        self.root_oid = root_oid
        self.username = username
        self.password = password
        self.session = None

    # ----- 세션 -----
    def login(self):
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
        s.get(self.base_url + "/auth/login/loginView.do", timeout=TIMEOUT)
        r = s.post(
            self.base_url + "/auth/login/login.do?",
            data={
                "user_id": self.username,
                "password": xor_encrypt(self.password),
                "loginType": "",
                "autoLogin": "false",
                "timezone": "Asia/Seoul",
            },
            timeout=TIMEOUT,
        )
        if "로그인" not in r.text and "loginContext" not in r.text:
            raise EcmClientError(f"로그인 실패: HTTP {r.status_code}")
        if not s.cookies.get("SESSION_KEY"):
            raise EcmClientError("로그인은 되었으나 SESSION_KEY 쿠키가 없습니다.")
        self.session = s
        return s

    def sess(self):
        if self.session is None:
            return self.login()
        return self.session

    @staticmethod
    def _looks_like_login(response) -> bool:
        """세션 만료로 로그인 페이지가 대신 돌아온 경우를 감지한다."""
        if response.status_code == 401:
            return True
        final_url = str(getattr(response, "url", "") or "")
        return "loginView.do" in final_url or "/auth/login/" in final_url

    def _post(self, path: str, **kwargs):
        """세션 만료 시 1회 자동 재로그인하는 POST 래퍼(결정 2)."""
        r = self.sess().post(self.base_url + path, timeout=TIMEOUT, **kwargs)
        if self._looks_like_login(r):
            self.login()
            r = self.session.post(self.base_url + path, timeout=TIMEOUT, **kwargs)
        return r

    # ----- 폴더/파일 조회 -----
    def children(self, oid: str) -> list:
        r = self._post(
            "/folder/folderExt.do?method=getChildren",
            data={"OID": oid},
        )
        text = (r.text or "").strip()
        if text.startswith("["):
            return r.json()
        if text.startswith("{"):
            data = r.json()
            return (data.get("params", {}) or {}).get("children") or data.get("children") or []
        return []

    @staticmethod
    def oid(row: dict) -> str:
        return row.get("OID") or row.get("oid") or ""

    @staticmethod
    def collect_files(obj, out: list) -> None:
        """중첩 JSON 을 재귀 순회해 fileName+storageFileID 노드를 파일로 수집한다."""
        if isinstance(obj, dict):
            if obj.get("fileName") and obj.get("storageFileID"):
                out.append({
                    "fileName": obj.get("fileName") or "",
                    "fileOID": obj.get("OID") or "",
                    "storageFileID": obj.get("storageFileID") or "",
                    "fileSize": int(float(obj.get("fileSize") or 0)),
                    "drm": bool(str(obj.get("drmStatus") or "").strip()),
                })
            for value in obj.values():
                DestinyECM.collect_files(value, out)
        elif isinstance(obj, list):
            for value in obj:
                DestinyECM.collect_files(value, out)

    def files(self, oid: str) -> list:
        form = {
            "listDataColumns[DO][0]": "OID",
            "listDataColumns[DO][1]": "objectType",
            "listDataColumns[DO][2]": "files",
            "listDataColumns[FL][0]": "OID",
            "listDataColumns[FL][1]": "fileName",
            "listDataColumns[FL][2]": "storageFileID",
            "listDataColumns[FL][3]": "fileSize",
            "listDataColumns[FL][4]": "drmStatus",
            "pageunit": "300",
            "OID": oid,
            "folderType": "C",
            "init": "true",
        }
        r = self._post(
            "/document/documentList.do?method=getDocumentListData",
            data=form,
        )
        out: list = []
        self.collect_files(r.json(), out)
        seen = set()
        deduped = []
        for f in out:
            key = f.get("storageFileID")
            if key and key not in seen:
                seen.add(key)
                deduped.append(f)
        return deduped

    def folder_contents(self, oid: str) -> dict:
        folders = []
        for child in self.children(oid):
            child_oid = self.oid(child)
            if child_oid:
                folders.append({"name": child.get("name", ""), "oid": child_oid})
        return {"folders": folders, "files": self.files(oid)}

    # ----- 다운로드 -----
    def download_bytes(self, file_meta: dict) -> bytes:
        session_key = self.sess().cookies.get("SESSION_KEY", "")
        file_name = file_meta["fileName"]
        file_ext = file_name.rsplit(".", 1)[-1] if "." in file_name else ""
        params = {
            "Method": "get",
            "BLOBType": "doc",
            "FileStatus": "N",
            "FileSize": str(int(float(file_meta.get("fileSize") or 0))),
            "FileID": file_meta["storageFileID"],
            "Mode": "save",
            "UseHistory": "true",
            "Browser": "unknown",
            "FileName": file_name,
            "FileOID": file_meta.get("fileOID") or file_meta.get("OID") or "",
            "FileExt": file_ext,
            "clientType": "W",
            "localShare": "false",
            # 핵심: 에이전트 복호화용 암호화 스트림을 받지 않으려면 false 여야 한다.
            "encryptionClient": "false",
            "DownloadAt": "webBrowser",
            "DownloadTo": "localDrive",
        }

        def _do_download():
            headers = {
                "Authorization": "Basic " + base64.b64encode(
                    self.sess().cookies.get("SESSION_KEY", session_key).encode()
                ).decode(),
                "User-Agent": "DestinyECM",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            return self.session.post(
                self.base_url + "/servlet/blob?" + urllib.parse.urlencode(params),
                headers=headers,
                data="",
                timeout=DOWNLOAD_TIMEOUT,
            )

        self.sess()  # 세션 보장
        r = _do_download()
        if self._looks_like_login(r):
            self.login()
            r = _do_download()
        if r.status_code != 200:
            raise EcmClientError(f"다운로드 실패: HTTP {r.status_code}")
        return r.content

    # ----- 프로젝트 폴더 자동 탐색 (test_no 기반, 결정 4·5) -----
    @staticmethod
    def year_candidates(test_no: str, cert_date: str = "") -> list:
        years = []
        m = re.search(r"(20\d\d)", cert_date or "")
        if m:
            years.append(m.group(1))
        m = re.search(r"-(\d{2})-", test_no or "")
        if m:
            years.append("20" + m.group(1))
        return list(dict.fromkeys(years))

    @staticmethod
    def test_no_patterns(test_no: str) -> list:
        test_no = (test_no or "").strip()
        patterns = [re.compile(re.escape(test_no) + r"(?!\d)")]
        m = re.match(r"(.+?-)(0*\d+)$", test_no)
        if m:
            prefix, tail = m.groups()
            flex = re.escape(prefix) + r"0*" + str(int(tail)) + r"(?!\d)"
            if flex != patterns[0].pattern:
                patterns.append(re.compile(flex))
        return patterns

    @staticmethod
    def is_template_folder(name: str) -> bool:
        return any(t in name for t in ("XXXXX", "XXXX", "xxx", "샘플", "Sample", "sample", "구조복사"))

    @staticmethod
    def project_match_score(name: str, *, exact: bool = False, root: str = "") -> int:
        score = 0
        if exact:
            score += 8
        if "완료" in name:
            score += 50
        elif "종료" in name:
            score += 45
        elif "재계약" in name:
            score += 35
        elif "계약" in name:
            score += 25
        elif "신청" in name:
            score += 15
        elif "시험대기" in name:
            score += 5
        if "취소" in name:
            score -= 50
        if "복사본" in name or "copy" in name.lower():
            score -= 20
        if "이관" in root:
            score -= 2
        return score

    def find_year_folder(self, year: str):
        for child in self.children(self.root_oid):
            name = str(child.get("name", ""))
            if year in name and "시험서비스" in name:
                return self.oid(child)
        return None

    def gs_candidate_roots(self, service_oid: str, grade: str = "") -> list:
        roots = [(service_oid, "")]
        for child in self.children(service_oid):
            name = str(child.get("name", ""))
            oid = self.oid(child)
            if not oid or "GS" not in name or "심의위원회" in name:
                continue
            if grade == "1" and "2등급" in name:
                continue
            if grade == "2" and "1등급" in name:
                continue
            roots.append((oid, name))
        deduped = []
        seen = set()
        for oid, name in roots:
            if oid not in seen:
                seen.add(oid)
                deduped.append((oid, name))
        return deduped

    def find_project_folder(self, test_no: str, cert_date: str = "", grade: str = ""):
        patterns = self.test_no_patterns(test_no)
        candidates = []
        for year in self.year_candidates(test_no, cert_date):
            service_oid = self.find_year_folder(year)
            if not service_oid:
                continue
            for root_oid, root_name in self.gs_candidate_roots(service_oid, grade):
                for child in self.children(root_oid):
                    name = str(child.get("name", ""))
                    if self.is_template_folder(name):
                        continue
                    exact = bool(re.search(re.escape(test_no) + r"(?!\d)", name))
                    if exact or any(p.search(name) for p in patterns):
                        candidates.append({
                            "oid": self.oid(child),
                            "name": name,
                            "year": year,
                            "root": root_name,
                            "_score": self.project_match_score(name, exact=exact, root=root_name),
                        })
        if not candidates:
            return None
        candidates.sort(key=lambda x: x["_score"], reverse=True)
        best = dict(candidates[0])
        best.pop("_score", None)
        return best


def build_client(center_code: str = "") -> DestinyECM:
    """센터 정의(설정)에서 base_url·root_oid·자격증명을 읽어 클라이언트를 만든다."""
    from main.views.review.ecm_download_review_centers import (
        ecm_base_url,
        ecm_credentials,
        ecm_root_oid,
    )

    username, password = ecm_credentials(center_code)
    if not username or not password:
        raise EcmClientError(
            f"ECM 자격증명이 설정되지 않았습니다(center={center_code!r}). "
            "환경변수 ECM_USERNAME/ECM_PASSWORD[_BUNDANG] 를 설정하세요."
        )
    return DestinyECM(
        base_url=ecm_base_url(center_code),
        root_oid=ecm_root_oid(center_code),
        username=username,
        password=password,
    )
