# Codex Skills

이 폴더는 다른 개발 PC에서 같은 Codex 작업 지침을 설치할 수 있도록 로컬 skill 원본을 보관한다.

Codex가 자동으로 이 폴더를 skill로 읽는 것은 아니다.
새 PC에서는 필요한 skill 폴더를 해당 PC의 `.codex\skills` 아래로 복사해야 한다.

## 설치 예시

PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force `
  ".\main\docs\codex_skills\gscert-download-review-maintainer" `
  "$env:USERPROFILE\.codex\skills\gscert-download-review-maintainer"
```

설치 후 새 Codex 대화에서 `gscert-download-review-maintainer` skill이 사용 가능해야 한다.

