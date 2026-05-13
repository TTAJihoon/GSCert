const maxRetryCount = 2;
const apiEndpoints = {
  projects: "/api/projects/?limit=500",
  jobs: "/api/jobs/",
  activeJob: "/api/jobs/active/"
};

const ruleNames = [
  "프로젝트번호 파일명 포함",
  "zip 파일 손상 여부",
  "최상위 폴더 구조",
  "시험성적서 PDF 존재",
  "계약서 존재",
  "SW저작권확인서 존재",
  "신청서 존재",
  "제품설명서 존재",
  "시험환경 정보 존재",
  "버전명 일치",
  "회사명 일치",
  "제품명 일치",
  "인증일자 표기",
  "시험PL 표기",
  "결과보고서 표지 값",
  "결과보고서 표 값",
  "Excel 머리글 프로젝트번호",
  "Word 표 프로젝트번호",
  "첨부파일 수정일자",
  "빈 파일 여부",
  "중복 파일명 여부",
  "파일명 특수문자",
  "필수 디렉터리 존재",
  "PDF 텍스트 추출 가능",
  "DOCX XML 파싱 가능",
  "엑셀 시트명 확인",
  "보안 관련 산출물 존재",
  "검토 대상 제외 파일",
  "압축 내 경로 길이",
  "최종 산출물 개수"
];

function makeRules(seed, variant = "complete") {
  return ruleNames.map((name, index) => {
    const status =
      variant === "hold" && index < 3 ? "작업실패" :
      variant === "needs_fix" && index % 11 === seed % 5 ? "부적합" :
      "정상";

    return {
      no: index + 1,
      name,
      status,
      detail: status === "정상"
        ? "기준을 만족했습니다."
        : status === "작업실패"
          ? "자동화 작업이 실패해 규칙 점검까지 진행하지 못했습니다."
          : "부적합 항목입니다. 산출물 수정 후 다시 점검해야 합니다."
    };
  });
}

const seedProjects = [
  {
    number: "TTA-26-00009",
    certDate: "2026.05.08",
    company: "우리데이터 주식회사",
    product: "우리데이터클리닝 V1.0",
    pl: "박지훈",
    review: "완료",
    inspectionDate: "2026.05.12 20:42",
    contract: "있음",
    reportPdf: "대상",
    copyright: "대상",
    rules: makeRules(1)
  },
  {
    number: "TTA-26-00010",
    certDate: "2026.05.09",
    company: "에이치소프트",
    product: "SecureFlow 2.1",
    pl: "김준호",
    review: "수정 필요",
    inspectionDate: "2026.05.12 20:55",
    contract: "있음",
    reportPdf: "대상",
    copyright: "대상",
    rules: makeRules(2, "needs_fix")
  },
  {
    number: "TTA-26-00011",
    certDate: "2026.05.10",
    company: "다온테크",
    product: "DaonOps Cloud",
    pl: "이수민",
    review: "보류",
    inspectionDate: "-",
    contract: "미확인",
    reportPdf: "대상",
    copyright: "미대상",
    holdReason: "ecmlist.db의 회사명과 다운로드된 산출물의 회사명이 다릅니다. 담당자 확인 후 재점검이 필요합니다.",
    rules: makeRules(3, "hold")
  },
  {
    number: "TTA-26-00012",
    certDate: "2026.05.10",
    company: "넥스트랩",
    product: "NextLab QA Suite",
    pl: "박지훈",
    review: "미점검",
    inspectionDate: "-",
    contract: "있음",
    reportPdf: "대상",
    copyright: "대상",
    rules: []
  },
  {
    number: "TTA-26-00013",
    certDate: "2026.05.11",
    company: "그린인사이트",
    product: "GreenWatch v3",
    pl: "최유진",
    review: "보류",
    inspectionDate: "-",
    contract: "미확인",
    reportPdf: "대상",
    copyright: "대상",
    holdReason: "필수 산출물 중 SW저작권확인서가 zip 내부에서 확인되지 않았습니다.",
    rules: makeRules(4, "hold")
  }
];

const generatedCompanies = [
  "우리데이터 주식회사",
  "에이치소프트",
  "다온테크",
  "넥스트랩",
  "그린인사이트",
  "브릿지웨어",
  "유니온시스템",
  "라온플랫폼",
  "시큐어마인드",
  "클라우드팩토리"
];

const generatedProducts = [
  "DataClean V1.0",
  "SecureFlow 2.1",
  "DaonOps Cloud",
  "NextLab QA Suite",
  "GreenWatch v3",
  "BridgeHub",
  "UnionDesk",
  "RaonWorks",
  "MindGuard",
  "CloudFactory Manager"
];

const generatedPls = ["박지훈", "김준호", "이수민", "최유진", "정하늘"];
const generatedReviews = ["완료", "수정 필요", "미점검", "완료", "수정 필요", "보류"];

let mockProjects = Array.from({ length: 30 }, (_, index) => {
  const seed = seedProjects[index % seedProjects.length];
  const review = index < seedProjects.length
    ? seed.review
    : generatedReviews[index % generatedReviews.length];
  const number = `TTA-26-${String(index + 9).padStart(5, "0")}`;
  const company = index < seedProjects.length
    ? seed.company
    : `${generatedCompanies[index % generatedCompanies.length]} ${Math.floor(index / generatedCompanies.length) + 1}`;
  const product = index < seedProjects.length
    ? seed.product
    : `${generatedProducts[index % generatedProducts.length]} ${Math.floor(index / generatedProducts.length) + 1}`;

  const project = {
    ...seed,
    number,
    certDate: `2026.05.${String((index % 23) + 1).padStart(2, "0")}`,
    company,
    product,
    pl: index < seedProjects.length ? seed.pl : generatedPls[index % generatedPls.length],
    review,
    inspectionDate: review === "미점검" || review === "보류"
      ? "-"
      : `2026.05.${String((index % 23) + 1).padStart(2, "0")} ${String(20 + (index % 4)).padStart(2, "0")}:${String((index * 7) % 60).padStart(2, "0")}`,
    contract: index % 7 === 0 ? "미확인" : "있음",
    reportPdf: "대상",
    copyright: index % 5 === 0 ? "미대상" : "대상",
    rules: review === "미점검" || review === "보류"
      ? []
      : makeRules(index + 1, review === "수정 필요" ? "needs_fix" : "complete")
  };

  if (review === "보류") {
    project.holdReason = seed.holdReason || `${number} 산출물 일부가 기준 정보와 일치하지 않아 담당자 확인이 필요합니다.`;
  } else {
    delete project.holdReason;
  }

  return project;
});

const mockActiveJob = {
  id: "JOB-20260510-004",
  status: "running",
  total: 5,
  completed: 2,
  failed: 1,
  currentProject: "TTA-26-00012",
  currentStep: "전송현황 완료 대기: zip 생성 완료 여부를 확인하고 있습니다.",
  worker: {
    running: true,
    pid: "8420",
    heartbeat: "2026-05-10 14:32:21",
    stale: false
  },
  projects: [
    {
      number: "TTA-26-00009",
      company: "우리데이터 주식회사",
      product: "우리데이터클리닝 V1.0",
      status: "completed",
      step: "zip 파일 확인 완료",
      retry: 0,
      zip: "00009 TTA-26-00009(완료) 우리데이터 주식회사(우리데이터클리닝 V1.0).zip",
      error: "",
      errorDetail: ""
    },
    {
      number: "TTA-26-00010",
      company: "에이치소프트",
      product: "SecureFlow 2.1",
      status: "completed",
      step: "중복 파일 알림 처리 후 재시도 완료",
      retry: 1,
      zip: "00010 TTA-26-00010(완료) 에이치소프트(SecureFlow 2.1).zip",
      error: "",
      errorDetail: ""
    },
    {
      number: "TTA-26-00011",
      company: "다온테크",
      product: "DaonOps Cloud",
      status: "failed",
      step: "zip 파일 확인",
      retry: 2,
      zip: "",
      error: "zip 파일을 찾을 수 없음",
      errorDetail: "전송현황 창은 종료되었지만 다운로드 폴더에서 프로젝트번호 TTA-26-00011을 포함한 zip 파일이 발견되지 않았습니다. 같은 이름의 기존 폴더가 남아 있었는지, 시스템 알림 창에서 중복 파일 처리가 실패했는지 확인해야 합니다."
    },
    {
      number: "TTA-26-00012",
      company: "넥스트랩",
      product: "NextLab QA Suite",
      status: "running",
      step: "전송현황 완료 대기",
      retry: 0,
      zip: "",
      error: "",
      errorDetail: ""
    },
    {
      number: "TTA-26-00013",
      company: "그린인사이트",
      product: "GreenWatch v3",
      status: "pending",
      step: "대기",
      retry: 0,
      zip: "",
      error: "",
      errorDetail: ""
    }
  ]
};

const mockJobs = [
  {
    id: "JOB-20260510-003",
    requestedAt: "2026-05-10 09:10",
    completedAt: "2026-05-10 09:42",
    total: 3,
    success: 2,
    failed: 1,
    status: "completed",
    projects: [
      {
        number: "TTA-26-00004",
        company: "이노시큐어",
        product: "InnoGate",
        status: "success",
        zip: "00004 TTA-26-00004(완료) 이노시큐어(InnoGate).zip",
        failStep: "",
        error: "",
        errorDetail: ""
      },
      {
        number: "TTA-26-00005",
        company: "메타브릿지",
        product: "MetaBridge Hub",
        status: "failed",
        zip: "",
        failStep: "폴더 찾아보기",
        error: "다운로드 폴더 선택 실패",
        errorDetail: "폴더 찾아보기 창은 열렸지만 프로젝트 저장 폴더가 트리에 표시되지 않았습니다. AGENT_DOWNLOAD_BASE_DIR 경로와 프로젝트 폴더 사전 생성 여부를 확인해야 합니다."
      },
      {
        number: "TTA-26-00006",
        company: "오션소프트",
        product: "OceanDesk",
        status: "success",
        zip: "00006 TTA-26-00006(완료) 오션소프트(OceanDesk).zip",
        failStep: "",
        error: "",
        errorDetail: ""
      }
    ]
  },
  {
    id: "JOB-20260509-008",
    requestedAt: "2026-05-09 16:05",
    completedAt: "2026-05-09 17:22",
    total: 4,
    success: 4,
    failed: 0,
    status: "completed",
    projects: [
      {
        number: "TTA-26-00001",
        company: "코어링크",
        product: "CoreLink PMS",
        status: "success",
        zip: "00001 TTA-26-00001(완료) 코어링크(CoreLink PMS).zip",
        failStep: "",
        error: "",
        errorDetail: ""
      },
      {
        number: "TTA-26-00002",
        company: "비전아이",
        product: "VisionEye",
        status: "success",
        zip: "00002 TTA-26-00002(완료) 비전아이(VisionEye).zip",
        failStep: "",
        error: "",
        errorDetail: ""
      },
      {
        number: "TTA-26-00003",
        company: "제이테크",
        product: "J-Report",
        status: "success",
        zip: "00003 TTA-26-00003(완료) 제이테크(J-Report).zip",
        failStep: "",
        error: "",
        errorDetail: ""
      },
      {
        number: "TTA-26-00007",
        company: "알파랩",
        product: "AlphaTest",
        status: "success",
        zip: "00007 TTA-26-00007(완료) 알파랩(AlphaTest).zip",
        failStep: "",
        error: "",
        errorDetail: ""
      }
    ]
  }
];

const state = {
  selected: new Set(),
  focusedProject: mockProjects[0],
  resultJobId: null,
  resultFilter: "all",
  heartbeatWarning: false,
  emptyJob: false,
  forceEmptyPreview: false,
  selectionMessage: "",
  projectLoadError: "",
  activeJob: null,
  activeProjects: [],
  resultJobs: [],
  resultProjects: [],
  resultLoadError: "",
  resultProjectLoadError: ""
};

const statusLabel = {
  pending: ["대기", "badge-muted"],
  running: ["진행 중", "badge-run"],
  downloaded: ["다운로드 완료", "badge-run"],
  inspecting: ["검사 중", "badge-run"],
  completed: ["완료", "badge-success"],
  failed: ["실패", "badge-danger"],
  skipped: ["건너뜀", "badge-warn"],
  success: ["성공", "badge-success"],
  scheduled: ["예약중", "badge-warn"],
  queued: ["대기중", "badge-run"],
  canceled: ["취소", "badge-muted"],
  "예약됨": ["예약중", "badge-warn"],
  "예약중": ["예약중", "badge-warn"],
  "대기중": ["대기중", "badge-run"],
  "진행중": ["진행중", "badge-run"],
  "취소": ["취소", "badge-muted"],
  "요청 가능": ["요청 가능", "badge-muted"],
  "완료": ["완료", "badge-success"],
  "수정 필요": ["수정 필요", "badge-warn"],
  "보류": ["보류", "badge-danger"],
  "미점검": ["미점검", "badge-muted"],
  "X": ["미점검", "badge-muted"],
  "부적합": ["부적합", "badge-danger"],
  "작업실패": ["작업실패", "badge-danger"],
  "정상": ["정상", "badge-success"],
  "경고": ["경고", "badge-warn"],
  "오류": ["오류", "badge-danger"]
};

function qs(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#039;"
  })[char]);
}

function getCookie(name) {
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${name}=`))
    ?.split("=")
    .slice(1)
    .join("=") || "";
}

async function requestJson(url, options = {}) {
  const headers = {
    "Accept": "application/json",
    ...(options.headers || {})
  };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const csrfToken = getCookie("csrftoken");
  if (csrfToken) {
    headers["X-CSRFToken"] = decodeURIComponent(csrfToken);
  }

  const response = await fetch(url, {
    ...options,
    headers
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.message || "요청을 처리하지 못했습니다.");
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function normalizeReview(value) {
  const review = String(value || "").trim();
  if (!review || review === "X") return "미점검";
  return review;
}

function normalizeApiProject(item) {
  return {
    number: item.project_number,
    certDate: item.cert_date || "-",
    company: item.company || "",
    product: item.product || "",
    pl: item.pl || "",
    review: normalizeReview(item.review),
    inspectionDate: item.inspection_date || "-",
    activeJobId: item.active_job_id || "",
    activeJobStatus: item.active_job_status || "",
    activeJobStatusLabel: item.active_job_status_label || "",
    activeProjectStatus: item.active_project_status || "",
    activeProjectStatusLabel: item.active_project_status_label || "",
    activeStateLabel: item.active_state_label || "",
    contract: "",
    reportPdf: "",
    copyright: "",
    rules: []
  };
}

function normalizeApiJobProject(item) {
  return {
    id: item.id,
    jobId: item.job_id,
    number: item.project_number,
    company: item.company || "",
    product: item.product || "",
    status: item.status,
    statusLabel: item.status_label || item.status,
    review: item.review_status_label || item.review_status || "-",
    step: item.current_step || item.status_label || "-",
    retry: item.retry_count || 0,
    zip: item.zip_file_name || "-",
    error: item.error_message || "",
    errorDetail: item.error_detail || "",
    failStep: item.status === "failed" ? item.current_step : ""
  };
}

function normalizeApiJob(item) {
  return {
    id: item.id,
    requestedAt: formatDateTime(item.requested_at),
    completedAt: formatDateTime(item.completed_at || item.canceled_at || item.started_at || item.available_after),
    total: item.requested_project_count || 0,
    success: item.completed_project_count || 0,
    failed: item.failed_project_count || 0,
    status: item.status,
    statusLabel: item.status_label || item.status,
    cancelable: item.status === "scheduled" || item.status === "queued"
  };
}

function formatDateTime(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function badge(status) {
  const config = statusLabel[status] || [status, "badge-muted"];
  return `<span class="badge ${config[1]}">${escapeHtml(config[0])}</span>`;
}

function isProjectLocked(item) {
  return item.review === "완료" || Boolean(item.activeJobId);
}

function isProjectSelectable(item) {
  return !isProjectLocked(item);
}

function updateClock() {
  const now = new Date();
  qs("lastUpdated").textContent = now.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

function populateFilters() {
  const pls = ["전체", ...new Set(mockProjects.map((item) => item.pl))];
  const reviews = ["전체", ...new Set(mockProjects.map((item) => item.review))];
  qs("filterPl").innerHTML = pls.map((value) => `<option>${value}</option>`).join("");
  qs("filterStatus").innerHTML = reviews.map((value) => `<option>${value}</option>`).join("");
}

async function loadProjects() {
  state.projectLoadError = "";
  qs("projectRows").innerHTML = `
    <tr><td colspan="9" class="empty-cell">프로젝트 목록을 불러오는 중입니다.</td></tr>
  `;

  try {
    const payload = await requestJson(apiEndpoints.projects);
    mockProjects = payload.items.map(normalizeApiProject);
    state.selected.clear();
    state.focusedProject = mockProjects[0] || null;
    populateFilters();
    renderProjects();
    updateClock();
  } catch (error) {
    mockProjects = [];
    state.selected.clear();
    state.focusedProject = null;
    state.projectLoadError = error.message;
    populateFilters();
    renderProjects();
  }
}

function filteredProjects() {
  const project = qs("filterProject").value.trim().toLowerCase();
  const company = qs("filterCompany").value.trim().toLowerCase();
  const product = qs("filterProduct").value.trim().toLowerCase();
  const pl = qs("filterPl").value;
  const review = qs("filterStatus").value;

  return mockProjects.filter((item) => (
    (!project || item.number.toLowerCase().includes(project)) &&
    (!company || item.company.toLowerCase().includes(company)) &&
    (!product || item.product.toLowerCase().includes(product)) &&
    (pl === "전체" || item.pl === pl) &&
    (review === "전체" || item.review === review)
  ));
}

function renderProjects() {
  const rows = filteredProjects();
  state.selected.forEach((number) => {
    const item = mockProjects.find((project) => project.number === number);
    if (!item || isProjectLocked(item)) {
      state.selected.delete(number);
    }
  });

  if (state.projectLoadError) {
    qs("projectRows").innerHTML = `
      <tr><td colspan="9" class="empty-cell">${escapeHtml(state.projectLoadError)}</td></tr>
    `;
    qs("selectVisible").disabled = true;
    qs("selectVisible").checked = false;
    renderSelection();
    renderDetail();
    return;
  }

  if (rows.length === 0) {
    qs("projectRows").innerHTML = `
      <tr><td colspan="9" class="empty-cell">조회된 프로젝트가 없습니다.</td></tr>
    `;
    qs("selectVisible").disabled = true;
    qs("selectVisible").checked = false;
    renderSelection();
    renderDetail();
    return;
  }

  qs("projectRows").innerHTML = rows.map((item) => {
    const locked = isProjectLocked(item);
    const checked = !locked && state.selected.has(item.number) ? "checked" : "";
    const disabled = locked ? "disabled" : "";
    const selected = state.focusedProject?.number === item.number ? "selected" : "";
    const lockedClass = locked ? "completed-locked" : "";
    const hasDetail = item.review === "완료" || item.review === "수정 필요" || item.review === "보류";
    const activeLabel = item.activeStateLabel || "요청 가능";
    const checkboxLabel = item.activeStateLabel
      ? `${item.number} ${item.activeStateLabel} 상태`
      : `${item.number} 선택`;
    return `
      <tr class="${selected} ${lockedClass}" data-project-row="${item.number}">
        <td class="check-col">
          <input type="checkbox" data-project-check="${item.number}" ${checked} ${disabled} aria-label="${checkboxLabel}" title="${checkboxLabel}">
        </td>
        <td><strong>${item.number}</strong></td>
        <td>${item.certDate}</td>
        <td>${item.company}</td>
        <td>${item.product}</td>
        <td>${item.pl}</td>
        <td>${badge(item.review)}</td>
        <td>${badge(activeLabel)}</td>
        <td>
          <button class="mini-button" type="button" data-inspection-detail="${item.number}" ${hasDetail ? "" : "disabled"}>
            상세
          </button>
        </td>
      </tr>
    `;
  }).join("");

  const selectableRows = rows.filter(isProjectSelectable);
  qs("selectVisible").disabled = selectableRows.length === 0;
  qs("selectVisible").checked = selectableRows.length > 0 && selectableRows.every((item) => state.selected.has(item.number));
  bindProjectRows();
  renderSelection();
  renderDetail();
}

function bindProjectRows() {
  document.querySelectorAll("[data-project-check]").forEach((checkbox) => {
    checkbox.addEventListener("click", (event) => {
      event.stopPropagation();
      const number = checkbox.dataset.projectCheck;
      const item = mockProjects.find((project) => project.number === number);
      if (!item || isProjectLocked(item)) return;
      state.selectionMessage = "";
      if (checkbox.checked) {
        state.selected.add(number);
      } else {
        state.selected.delete(number);
      }
      renderProjects();
    });
  });

  document.querySelectorAll("[data-inspection-detail]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openInspectionModal(button.dataset.inspectionDetail);
    });
  });

  document.querySelectorAll("[data-project-row]").forEach((row) => {
    row.addEventListener("click", () => {
      state.focusedProject = mockProjects.find((item) => item.number === row.dataset.projectRow);
      renderProjects();
    });
  });
}

function renderSelection() {
  const selected = [...state.selected];
  const hasSelection = selected.length > 0;
  qs("selectionCount").textContent = `${selected.length}개 선택됨`;
  qs("selectionList").innerHTML = selected.length
    ? selected.map((number) => {
      const item = mockProjects.find((project) => project.number === number);
      return `
        <div class="selection-chip">
          <strong>${number}</strong>
          <span>${item?.company || ""}</span>
        </div>
      `;
    }).join("")
    : `<p class="muted">선택된 프로젝트가 없습니다.</p>`;

  qs("lockMessage").textContent = state.selectionMessage || (state.emptyJob
    ? "선택한 프로젝트는 요청 순서대로 대기열에 등록됩니다."
    : "현재 다른 작업이 진행 중입니다. 요청하면 예약됨 상태로 등록됩니다.");
  qs("requestJob").disabled = !hasSelection;
}

function renderDetail() {
  const item = state.focusedProject;
  if (!item) {
    qs("projectDetail").innerHTML = `
      <h3>프로젝트 정보</h3>
      <p class="muted">목록에서 행을 선택하면 프로젝트 정보를 표시합니다.</p>
    `;
    return;
  }

  qs("projectDetail").innerHTML = `
    <h3>${item.number}</h3>
    <dl class="detail-list">
      <dt>인증일자</dt><dd>${item.certDate}</dd>
      <dt>회사명</dt><dd>${item.company}</dd>
      <dt>제품명</dt><dd>${item.product}</dd>
      <dt>시험PL</dt><dd>${item.pl}</dd>
      <dt>점검결과</dt><dd>${badge(item.review)}</dd>
      <dt>작업상태</dt><dd>${badge(item.activeStateLabel || "요청 가능")}</dd>
      <dt>점검날짜</dt><dd>${item.inspectionDate || "-"}</dd>
    </dl>
  `;
}

async function refreshActiveJob() {
  try {
    const payload = await requestJson(apiEndpoints.activeJob);
    state.activeJob = payload.active_job;
    state.emptyJob = !payload.active_job;
    if (state.activeJob) {
      const projectsPayload = await requestJson(`/api/jobs/${state.activeJob.id}/projects/`);
      state.activeProjects = projectsPayload.items.map(normalizeApiJobProject);
    } else {
      state.activeProjects = [];
    }
  } catch (error) {
    state.activeJob = null;
    state.activeProjects = [];
    state.emptyJob = true;
  }
  renderProgress();
  renderSelection();
}

async function loadResultJobs(preferredJobId = null) {
  state.resultLoadError = "";
  qs("jobList").innerHTML = `<p class="muted">작업 목록을 불러오는 중입니다.</p>`;
  qs("resultRows").innerHTML = `
    <tr><td colspan="9" class="empty-cell">작업을 불러오는 중입니다.</td></tr>
  `;

  try {
    const payload = await requestJson(`${apiEndpoints.jobs}?status=all&limit=50`);
    state.resultJobs = payload.items.map(normalizeApiJob);
    state.resultJobId = preferredJobId
      || (state.resultJobs.some((job) => job.id === state.resultJobId) ? state.resultJobId : null)
      || state.resultJobs[0]?.id
      || null;
    renderJobs();
    await loadResultProjects();
  } catch (error) {
    state.resultJobs = [];
    state.resultProjects = [];
    state.resultJobId = null;
    state.resultLoadError = error.message;
    state.resultProjectLoadError = "";
    renderJobs();
    renderResults();
  }
}

async function loadResultProjects() {
  if (!state.resultJobId) {
    state.resultProjects = [];
    renderResults();
    return;
  }

  qs("resultRows").innerHTML = `
    <tr><td colspan="9" class="empty-cell">프로젝트별 결과를 불러오는 중입니다.</td></tr>
  `;

  try {
    const payload = await requestJson(`/api/jobs/${state.resultJobId}/projects/`);
    state.resultProjects = payload.items.map(normalizeApiJobProject);
    state.resultProjectLoadError = "";
    renderResults();
  } catch (error) {
    state.resultProjects = [];
    state.resultProjectLoadError = error.message;
    renderResults();
  }
}

function renderProgress() {
  const showEmpty = state.forceEmptyPreview || (!state.activeJob && state.emptyJob);
  qs("activeProgressView").hidden = showEmpty;
  qs("emptyProgressView").hidden = !showEmpty;

  if (showEmpty) {
    qs("activeJobState").innerHTML = `
      <span class="dot dot-muted"></span>
      <div><span class="label">현재 작업</span><strong>작업 없음</strong></div>
    `;
    return;
  }

  const activeJob = state.activeJob || mockActiveJob;
  const activeProjects = state.activeJob ? state.activeProjects : mockActiveJob.projects;
  const currentProject = activeProjects.find((item) => item.status === "running") || activeProjects[0];
  const total = activeJob.requested_project_count ?? activeJob.total;
  const completed = activeJob.completed_project_count ?? activeJob.completed;
  const failed = activeJob.failed_project_count ?? activeJob.failed;
  const progressPercent = activeJob.progress_percent ?? (total ? Math.round((completed / total) * 100) : 0);

  qs("activeJobState").innerHTML = `
    <span class="dot dot-run"></span>
    <div><span class="label">현재 작업</span><strong>${activeJob.status_label || "진행 중"}</strong></div>
  `;
  qs("jobId").textContent = activeJob.id;
  qs("jobProgress").textContent = `${completed} / ${total}`;
  qs("currentProject").textContent = currentProject?.number || "-";
  qs("failedCount").textContent = `${failed}건`;
  qs("currentStep").textContent = activeJob.progress_message || currentProject?.step || "-";
  qs("progressBar").style.width = `${progressPercent}%`;

  const worker = {
    ...(activeJob.worker || mockActiveJob.worker),
    stale: state.heartbeatWarning,
    heartbeat: state.heartbeatWarning ? "2026-05-10 14:20:03" : (activeJob.worker?.heartbeat_at || mockActiveJob.worker.heartbeat)
  };

  qs("workerBox").className = `worker-box ${worker.stale ? "warning" : ""}`;
  qs("workerBox").innerHTML = `
    <div>
      <strong>${worker.stale ? "작업 실행기의 heartbeat가 지연되고 있습니다." : "작업 실행기가 정상 동작 중입니다."}</strong>
      <div>PID ${worker.pid || "-"} · 마지막 heartbeat ${worker.heartbeat || "-"}</div>
    </div>
    <span class="badge ${worker.stale ? "badge-warn" : "badge-success"}">${worker.stale ? "지연" : "정상"}</span>
  `;

  qs("workerState").innerHTML = `
    <span class="dot ${worker.stale ? "dot-warn" : "dot-ok"}"></span>
    <div><span class="label">Worker</span><strong>${worker.stale ? "지연" : "실행 중"}</strong></div>
  `;

  qs("progressRows").innerHTML = activeProjects.length ? activeProjects.map((item, index) => `
    <tr>
      <td>${index + 1}</td>
      <td><strong>${escapeHtml(item.number)}</strong></td>
      <td>${escapeHtml(item.company)}</td>
      <td>${escapeHtml(item.product)}</td>
      <td>${badge(item.status)}</td>
      <td>${escapeHtml(item.step)}</td>
      <td>${item.retry} / ${maxRetryCount}</td>
      <td>${escapeHtml(item.zip || "-")}</td>
      <td>${item.error ? `<button class="link-button" type="button" data-error-detail="progress:${escapeHtml(item.id || item.number)}">${escapeHtml(item.error)}</button>` : "-"}</td>
    </tr>
  `).join("") : `
    <tr><td colspan="9" class="empty-cell">작업은 있지만 프로젝트별 진행 정보가 아직 없습니다.</td></tr>
  `;

  bindErrorButtons();
}

function renderJobs() {
  if (state.resultLoadError && state.resultJobs.length === 0) {
    qs("jobList").innerHTML = `<p class="muted">${escapeHtml(state.resultLoadError)}</p>`;
    return;
  }

  if (state.resultJobs.length === 0) {
    qs("jobList").innerHTML = `<p class="muted">조회된 작업이 없습니다.</p>`;
    return;
  }

  qs("jobList").innerHTML = state.resultJobs.map((job) => `
    <article class="job-card ${state.resultJobId === job.id ? "active" : ""}" role="button" tabindex="0" data-job-id="${escapeHtml(job.id)}">
      <div class="job-title">
        <span>${escapeHtml(job.id)}</span>
        ${badge(job.statusLabel || job.status)}
      </div>
      <div class="job-meta">
        <span>요청 ${escapeHtml(job.requestedAt)}</span>
        <span>기준시각 ${escapeHtml(job.completedAt)}</span>
        <span>전체 ${job.total}</span>
        <span>완료 ${job.success} / 실패 ${job.failed}</span>
      </div>
      ${job.cancelable ? `
        <div class="job-card-actions">
          <button class="mini-button danger-action" type="button" data-cancel-job="${escapeHtml(job.id)}">
            예약 취소
          </button>
        </div>
      ` : ""}
    </article>
  `).join("");

  document.querySelectorAll("[data-job-id]").forEach((card) => {
    const selectJob = async () => {
      state.resultJobId = card.dataset.jobId;
      renderJobs();
      await loadResultProjects();
    };
    card.addEventListener("click", selectJob);
    card.addEventListener("keydown", async (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      await selectJob();
    });
  });

  document.querySelectorAll("[data-cancel-job]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const job = state.resultJobs.find((item) => item.id === button.dataset.cancelJob);
      if (job) openCancelJobModal(job);
    });
  });
}

function renderResults() {
  const job = state.resultJobs.find((item) => item.id === state.resultJobId);
  if (!job) {
    qs("resultCaption").textContent = "작업을 선택하면 프로젝트별 결과를 표시합니다.";
    qs("resultRows").innerHTML = `
      <tr><td colspan="9" class="empty-cell">${state.resultLoadError ? escapeHtml(state.resultLoadError) : "조회된 작업이 없습니다."}</td></tr>
    `;
    return;
  }

  qs("resultCaption").textContent = `${job.id} · 완료 ${job.success}건 · 실패 ${job.failed}건`;

  if (state.resultProjectLoadError) {
    qs("resultRows").innerHTML = `
      <tr><td colspan="9" class="empty-cell">${escapeHtml(state.resultProjectLoadError)}</td></tr>
    `;
    return;
  }

  const rows = state.resultProjects.filter((item) => (
    state.resultFilter === "all" ||
    (state.resultFilter === "success" && (item.status === "success" || item.status === "completed")) ||
    (state.resultFilter === "failed" && item.status === "failed")
  ));

  if (rows.length === 0) {
    qs("resultRows").innerHTML = `
      <tr><td colspan="9" class="empty-cell">표시할 프로젝트 결과가 없습니다.</td></tr>
    `;
    return;
  }

  qs("resultRows").innerHTML = rows.map((item) => `
    <tr>
      <td><strong>${escapeHtml(item.number)}</strong></td>
      <td>${escapeHtml(item.company)}</td>
      <td>${escapeHtml(item.product)}</td>
      <td>${badge(item.statusLabel || item.status)}</td>
      <td>${badge(item.review)}</td>
      <td>
        <button class="mini-button" type="button" data-rule-result="${escapeHtml(item.id)}">
          상세
        </button>
      </td>
      <td>${escapeHtml(item.zip || "-")}</td>
      <td>${escapeHtml(item.failStep || "-")}</td>
      <td>${item.error ? `<button class="link-button" type="button" data-error-detail="result:${escapeHtml(item.id)}">${escapeHtml(item.error)}</button>` : "-"}</td>
    </tr>
  `).join("");

  bindRuleResultButtons();
  bindErrorButtons();
}

function openModal({ eyebrow, title, body }) {
  qs("modalEyebrow").textContent = eyebrow;
  qs("modalTitle").textContent = title;
  qs("modalBody").innerHTML = body;
  qs("detailModal").hidden = false;
}

function closeModal() {
  qs("detailModal").hidden = true;
}

function openRequestCompleteModal(payload, requestedCount) {
  openModal({
    eyebrow: "작업 요청",
    title: "작업 요청 완료",
    body: `
      <div class="modal-message success">
        <strong>${escapeHtml(payload.message || "작업 요청이 등록되었습니다.")}</strong>
        <p>요청 프로젝트 ${requestedCount}건 · 작업 ID ${escapeHtml(payload.job_id || "-")}</p>
        <p>현재 상태: ${escapeHtml(payload.status_label || payload.status || "-")}</p>
      </div>
    `
  });
}

function openCancelJobModal(job) {
  openModal({
    eyebrow: "예약 취소",
    title: `${job.id} 작업 취소`,
    body: `
      <div class="modal-message warning">
        <strong>예약됨 또는 대기중인 작업을 취소합니다.</strong>
        <p>취소된 작업은 다시 실행되지 않으며, 같은 프로젝트는 필요할 때 다시 작업 요청할 수 있습니다.</p>
      </div>
      <div class="modal-actions">
        <button class="secondary-button" type="button" data-close-cancel-modal>닫기</button>
        <button class="primary-button danger-action" type="button" data-confirm-cancel-job="${escapeHtml(job.id)}">취소 실행</button>
      </div>
    `
  });
  qs("modalBody").querySelector("[data-close-cancel-modal]").addEventListener("click", closeModal);
  qs("modalBody").querySelector("[data-confirm-cancel-job]").addEventListener("click", async (event) => {
    await cancelJob(event.currentTarget.dataset.confirmCancelJob);
  });
}

async function cancelJob(jobId) {
  const button = qs("modalBody").querySelector("[data-confirm-cancel-job]");
  if (button) {
    button.disabled = true;
    button.textContent = "취소 중";
  }

  try {
    const payload = await requestJson(`/api/jobs/${jobId}/cancel/`, { method: "POST" });
    openModal({
      eyebrow: "예약 취소",
      title: "작업 취소 완료",
      body: `
        <div class="modal-message success">
          <strong>${escapeHtml(payload.message || "예약된 작업을 취소했습니다.")}</strong>
          <p>취소된 프로젝트는 프로젝트 선택 탭에서 다시 요청할 수 있습니다.</p>
        </div>
      `
    });
    await Promise.allSettled([
      refreshActiveJob(),
      loadProjects(),
      loadResultJobs(jobId)
    ]);
  } catch (error) {
    openModal({
      eyebrow: "예약 취소",
      title: "작업 취소 실패",
      body: `
        <div class="modal-message warning">
          <strong>${escapeHtml(error.message)}</strong>
          <p>이미 실행 중이거나 완료된 작업은 취소할 수 없습니다.</p>
        </div>
      `
    });
  }
}

function openInspectionModal(projectNumber) {
  const project = mockProjects.find((item) => item.number === projectNumber);
  if (!project) return;

  if (project.review === "보류") {
    openModal({
      eyebrow: "작업 실패",
      title: `${project.number} 작업 보류`,
      body: `
        <div class="modal-message warning">
          <strong>${escapeHtml(project.holdReason)}</strong>
          <p>작업 자체가 실패했기 때문에 점검 규칙 결과는 생성되지 않았습니다. 원인을 확인한 뒤 다시 작업을 요청해야 합니다.</p>
        </div>
      `
    });
    return;
  }

  const rows = project.rules.map((rule) => `
    <tr>
      <td>${rule.no}</td>
      <td>${escapeHtml(rule.name)}</td>
      <td>${badge(rule.status)}</td>
      <td>${escapeHtml(rule.detail)}</td>
    </tr>
  `).join("");

  openModal({
    eyebrow: "점검 결과",
    title: `${project.number} 규칙별 점검 결과`,
    body: project.rules.length ? `
      <p class="modal-lead">약 30개 점검 규칙을 표로 확인하는 화면입니다. 실제 규칙 정의 후 컬럼은 확장할 수 있습니다.</p>
      <div class="table-wrap modal-table">
        <table class="data-table">
          <thead>
            <tr>
              <th>번호</th>
              <th>점검항목</th>
              <th>결과</th>
              <th>상세</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    ` : `
      <div class="modal-message warning">
        <strong>이 프로젝트의 규칙 결과는 결과 조회 탭에서 확인해야 합니다.</strong>
        <p>작업 이력과 연결된 실제 규칙 결과는 결과 조회 탭의 프로젝트 상세 버튼으로 조회합니다.</p>
      </div>
    `
  });
}

function findErrorItem(source, number) {
  if (source === "progress") {
    return state.activeProjects.find((item) => item.id === number || item.number === number)
      || mockActiveJob.projects.find((item) => item.id === number || item.number === number);
  }

  return state.resultProjects.find((item) => item.id === number);
}

async function openResultRulesModal(jobProjectId) {
  const project = state.resultProjects.find((item) => item.id === jobProjectId);
  if (!project) return;

  openModal({
    eyebrow: "점검 결과",
    title: `${project.number} 규칙별 점검 결과`,
    body: `<p class="modal-lead">점검 결과를 불러오는 중입니다.</p>`
  });

  try {
    const payload = await requestJson(`/api/job-projects/${jobProjectId}/results/`);
    const rows = payload.items.map((rule) => `
      <tr>
        <td>${rule.sequence}</td>
        <td>${escapeHtml(rule.rule_name)}</td>
        <td>${badge(rule.status_label || rule.status)}</td>
        <td>${escapeHtml(rule.file_name || "-")}</td>
        <td>${escapeHtml(rule.expected || "-")}</td>
        <td>${escapeHtml(rule.actual || "-")}</td>
        <td>${escapeHtml(rule.message || "-")}</td>
      </tr>
    `).join("");

    qs("modalBody").innerHTML = payload.items.length
      ? `
        <div class="table-wrap modal-table">
          <table class="data-table">
            <thead>
              <tr>
                <th>번호</th>
                <th>점검항목</th>
                <th>결과</th>
                <th>파일명</th>
                <th>기대값</th>
                <th>실제값</th>
                <th>상세</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      `
      : `
        <div class="modal-message warning">
          <strong>생성된 규칙 결과가 없습니다.</strong>
          <p>작업 자체가 실패했거나 아직 규칙 검사가 실행되지 않은 프로젝트입니다.</p>
        </div>
      `;
  } catch (error) {
    qs("modalBody").innerHTML = `
      <div class="modal-message warning">
        <strong>${escapeHtml(error.message)}</strong>
        <p>규칙 결과를 다시 조회해 주세요.</p>
      </div>
    `;
  }
}

function bindRuleResultButtons() {
  document.querySelectorAll("[data-rule-result]").forEach((button) => {
    button.addEventListener("click", () => {
      openResultRulesModal(button.dataset.ruleResult);
    });
  });
}

function bindErrorButtons() {
  document.querySelectorAll("[data-error-detail]").forEach((button) => {
    button.addEventListener("click", () => {
      const [source, number] = button.dataset.errorDetail.split(":");
      const item = findErrorItem(source, number);
      if (!item) return;

      openModal({
        eyebrow: "오류 상세",
        title: `${item.number} 실패 상세`,
        body: `
          <dl class="error-detail-list">
            <dt>실패 단계</dt><dd>${escapeHtml(item.failStep || item.step || "-")}</dd>
            <dt>오류 요약</dt><dd>${escapeHtml(item.error || "-")}</dd>
            <dt>상세 내용</dt><dd>${escapeHtml(item.errorDetail || "상세 로그가 없습니다.")}</dd>
            <dt>재시도</dt><dd>${item.retry ?? "-"} / ${maxRetryCount}</dd>
          </dl>
        `
      });
    });
  });
}

function bindControls() {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab-button").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      qs(`tab-${button.dataset.tab}`).classList.add("active");
    });
  });

  ["filterProject", "filterCompany", "filterProduct", "filterPl", "filterStatus"].forEach((id) => {
    qs(id).addEventListener("input", renderProjects);
  });

  qs("refreshProjects").addEventListener("click", () => {
    loadProjects();
    qs("refreshProjects").innerHTML = `<i class="fa-solid fa-check"></i> 갱신 완료`;
    setTimeout(() => {
      qs("refreshProjects").innerHTML = `<i class="fa-solid fa-rotate-right"></i> DB 새로고침`;
    }, 1200);
  });

  qs("selectVisible").addEventListener("change", () => {
    state.selectionMessage = "";
    filteredProjects().forEach((item) => {
      if (!isProjectSelectable(item)) return;
      if (qs("selectVisible").checked) {
        state.selected.add(item.number);
      } else {
        state.selected.delete(item.number);
      }
    });
    renderProjects();
  });

  qs("clearSelection").addEventListener("click", () => {
    state.selected.clear();
    state.selectionMessage = "";
    renderProjects();
  });

  qs("requestJob").addEventListener("click", async () => {
    const count = state.selected.size;
    if (count === 0) return;

    qs("requestJob").disabled = true;
    state.selectionMessage = "작업 요청을 등록하는 중입니다.";
    renderSelection();

    try {
      const payload = await requestJson(apiEndpoints.jobs, {
        method: "POST",
        body: JSON.stringify({ project_numbers: [...state.selected] })
      });
      state.selectionMessage = payload.message || `${count}개 프로젝트가 등록되었습니다.`;
      state.resultJobId = payload.job_id || state.resultJobId;
      state.selected.clear();
      await refreshActiveJob();
      await loadProjects();
      await loadResultJobs(payload.job_id);
      openRequestCompleteModal(payload, count);
    } catch (error) {
      state.selectionMessage = error.message;
      renderSelection();
    }
  });

  qs("toggleHeartbeat").addEventListener("click", () => {
    state.heartbeatWarning = !state.heartbeatWarning;
    renderProgress();
  });

  qs("toggleEmptyJob").addEventListener("click", () => {
    state.forceEmptyPreview = !state.forceEmptyPreview;
    qs("toggleEmptyJob").textContent = state.forceEmptyPreview ? "진행 작업 상태 보기" : "작업 없음 상태 보기";
    renderProgress();
  });

  document.querySelectorAll("[data-result-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-result-filter]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.resultFilter = button.dataset.resultFilter;
      renderResults();
    });
  });

  qs("closeModal").addEventListener("click", closeModal);
  qs("detailModal").addEventListener("click", (event) => {
    if (event.target === qs("detailModal")) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });
}

async function init() {
  updateClock();
  bindControls();
  populateFilters();
  renderProjects();
  await loadProjects();
  await refreshActiveJob();
  await loadResultJobs();
  setInterval(updateClock, 1000);
}

document.addEventListener("DOMContentLoaded", init);
