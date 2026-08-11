const maxRetryCount = 2;
const jobListPageSize = 5;
const apiEndpoints = {
  projects: "/api/projects/",
  jobs: "/api/jobs/",
  activeJob: "/api/jobs/active/",
  jobsForceStop: "/api/jobs/force-stop/",
  serverTime: "/api/server-time/",
  serverTimeAction: "/api/server-time/action/",
  plAssignments: "/api/pl-assignments/",
  plAssignmentsApply: "/api/pl-assignments/apply/"
};

const centerLabels = {
  sangam: "상암",
  bundang: "분당",
  yeongnam: "영남"
};

// 'PL 배정 목록' 모달 상태. 서버에서 받은 원본은 plAssignOriginalCenterByName에,
// 사용자가 좌/우 탭 사이에서 이동시키는 동안의 작업 중 상태는
// plAssignCurrentCenterByName에 둔다 - '확인'을 눌러야 둘의 차이만 서버에 반영된다.
let plAssignData = null;
let plAssignCountByName = {};
let plAssignOriginalCenterByName = {};
let plAssignCurrentCenterByName = {};
let plAssignActiveTab = { left: "", right: "" };
let plAssignSelected = { left: new Set(), right: new Set() };

function readJsonScript(id, fallback) {
  const node = document.getElementById(id);
  if (!node) return fallback;
  try {
    return JSON.parse(node.textContent || "");
  } catch (error) {
    return fallback;
  }
}

const parsedCenterRoutes = readJsonScript("downloadReviewCenterRoutes", {});
const centerRoutes = parsedCenterRoutes && typeof parsedCenterRoutes === "object" && !Array.isArray(parsedCenterRoutes)
  ? parsedCenterRoutes
  : {};
const parsedAllowedCenters = readJsonScript("downloadReviewAllowedCenters", Object.keys(centerLabels));
const allowedCenters = new Set(Array.isArray(parsedAllowedCenters) && parsedAllowedCenters.length
  ? parsedAllowedCenters
  : Object.keys(centerLabels));
const initialCenter = readJsonScript("downloadReviewDefaultCenter", "sangam") || "sangam";

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
  center: initialCenter,
  selected: new Set(),
  focusedProject: null,
  resultJobId: null,
  resultFilter: "all",
  resultJobCenter: "all",
  resultPagination: {
    total: 0,
    limit: jobListPageSize,
    offset: 0,
    hasMore: false
  },
  heartbeatWarning: false,
  emptyJob: false,
  forceEmptyPreview: false,
  selectionMessage: "",
  projectLoadError: "",
  projectFilters: defaultProjectFilters(),
  activeJob: null,
  hasAnyActiveJob: false,
  activeProjects: [],
  resultJobs: [],
  resultProjects: [],
  resultLoadError: "",
  resultProjectLoadError: "",
  lastCheckedIndex: -1,
  modalDownloadFilename: "",
  modalFullFolderProject: null,
  modalChangeNoteProject: null,
  manualOverrideTarget: null,
  inspectionRuleItems: [],
  inspectionItems: [],
  inspectionFilter: null,
  serverTime: null
};

function defaultProjectFilters() {
  return {
    project: "",
    company: "",
    product: "",
    pl: "",
    review: "전체"
  };
}

const projectRowsColumnLayout = {
  fixed: [43, 155, 123, null, null, 168, 101, 101, 74],
  variableMin: 400,
  variableRatio: [4, 6]
};

const tableColumnDefaults = {
  progressRows: [64, 145, 180, 220, 105, 260, 90, 105, 280],
  resultRows: [145, 180, 220, 105, 115, 80, 240, 145, 280],
  "규칙별 점검 결과": [60, 170, 76, 210, 230, 230, 250, 130]
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
  pass: ["정상", "badge-success"],
  fail: ["부적합", "badge-danger"],
  unsupported: ["미지원", "badge-muted"],
  error: ["오류", "badge-danger"],
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
  "O": ["완료", "badge-success"],
  "X": ["수정 필요", "badge-warn"],
  "부적합": ["부적합", "badge-danger"],
  "작업실패": ["작업실패", "badge-danger"],
  "정상": ["정상", "badge-success"],
  "경고": ["경고", "badge-warn"],
  "오류": ["오류", "badge-danger"]
};

function qs(id) {
  return document.getElementById(id);
}

function tableResizeKey(table) {
  const bodyId = table.querySelector("tbody")?.id || "";
  return bodyId || table.getAttribute("aria-label") || "";
}

function tableColumnStorageKey(key) {
  return `downloadReviewColumnWidths:${key}`;
}

function readStoredColumnWidths(key) {
  try {
    const parsed = JSON.parse(localStorage.getItem(tableColumnStorageKey(key)) || "[]");
    return Array.isArray(parsed) ? parsed.map((value) => Number(value)).filter(Boolean) : [];
  } catch (error) {
    return [];
  }
}

function writeStoredColumnWidths(key, widths) {
  try {
    localStorage.setItem(tableColumnStorageKey(key), JSON.stringify(widths.map((width) => Math.round(width))));
  } catch (error) {
    // localStorage may be disabled; resizing should still work for the current page.
  }
}

function ensureTableColumnGroup(table, widths) {
  let colgroup = table.querySelector(":scope > colgroup");
  if (!colgroup) {
    colgroup = document.createElement("colgroup");
    table.insertBefore(colgroup, table.firstElementChild);
  }

  colgroup.innerHTML = widths.map((width) => `<col style="width: ${width}px;">`).join("");
  table.style.width = `${widths.reduce((sum, width) => sum + width, 0)}px`;
  table.style.minWidth = table.style.width;
  return colgroup;
}

function projectRowsColumnWidths(table) {
  const wrap = table.parentElement;
  const available = wrap?.clientWidth || 0;
  const fixedTotal = projectRowsColumnLayout.fixed.reduce((sum, width) => sum + (width || 0), 0);
  const variableAvailable = Math.max(0, available - fixedTotal);
  const ratioTotal = projectRowsColumnLayout.variableRatio.reduce((sum, ratio) => sum + ratio, 0);
  const companyWidth = Math.max(
    projectRowsColumnLayout.variableMin,
    variableAvailable * projectRowsColumnLayout.variableRatio[0] / ratioTotal
  );
  const productWidth = Math.max(
    projectRowsColumnLayout.variableMin,
    variableAvailable * projectRowsColumnLayout.variableRatio[1] / ratioTotal
  );
  const variableWidths = [companyWidth, productWidth];
  let variableIndex = 0;

  return projectRowsColumnLayout.fixed.map((width) => {
    if (width) return width;
    const nextWidth = variableWidths[variableIndex] || projectRowsColumnLayout.variableMin;
    variableIndex += 1;
    return nextWidth;
  });
}

// 리사이즈 테이블은 열 너비 합으로 table 너비가 고정되어 컨테이너보다 좁으면
// 우측에 빈 공간이 생긴다. 컨테이너 폭에 맞게 열 너비를 비례 확대해 빈 공간을 없앤다.
function fitTableColumns(table) {
  const colgroup = table.querySelector(":scope > colgroup");
  if (!colgroup) return;
  const cols = Array.from(colgroup.children);
  if (!cols.length) return;
  const wrap = table.parentElement; // .table-wrap
  if (!wrap) return;
  const available = wrap.clientWidth;
  if (!available) return; // 숨겨진 탭 등 측정 불가

  const widths = cols.map((col) => parseFloat(col.style.width) || 0);
  const sum = widths.reduce((acc, value) => acc + value, 0);
  if (sum <= 0) return;
  if (sum >= available) return; // 이미 가득 차거나 넘침(가로 스크롤) → 그대로 둔다

  const scale = available / sum;
  cols.forEach((col, index) => {
    col.style.width = `${widths[index] * scale}px`;
  });
  table.style.width = `${available}px`;
  table.style.minWidth = `${available}px`;
}

// 현재 보이는 모든 리사이즈 테이블의 너비를 컨테이너에 맞춘다.
function fitVisibleResizableTables() {
  document.querySelectorAll(".data-table.resizable-table").forEach((table) => {
    if (table.offsetParent !== null) {
      fitTableColumns(table);
    }
  });
}

function initResizableTables() {
  document.querySelectorAll(".data-table").forEach((table, tableIndex) => {
    if (table.dataset.resizableReady === "true") return;
    const key = tableResizeKey(table) || `table-${tableIndex}`;
    const headers = Array.from(table.querySelectorAll("thead th"));
    if (!headers.length) return;

    const defaults = key === "projectRows"
      ? projectRowsColumnWidths(table)
      : tableColumnDefaults[key] || headers.map((header) => Math.max(90, Math.round(header.getBoundingClientRect().width || 120)));
    const stored = readStoredColumnWidths(key);
    const widths = headers.map((_, index) => stored[index] || defaults[index] || 120);
    const colgroup = ensureTableColumnGroup(table, widths);

    table.classList.add("resizable-table");
    table.dataset.resizableReady = "true";
    table.dataset.resizeKey = key;

    headers.forEach((header, index) => {
      header.classList.add("resizable-header");
      const handle = document.createElement("span");
      handle.className = "column-resize-handle";
      handle.setAttribute("role", "separator");
      handle.setAttribute("aria-orientation", "vertical");
      handle.setAttribute("aria-label", "열 너비 조정");
      header.appendChild(handle);

      let resizing = false;
      const startResize = (event, eventNames) => {
        if (resizing) return;
        resizing = true;
        event.preventDefault();
        event.stopPropagation();
        const startX = event.clientX;
        const startWidth = widths[index];
        const minWidth = header.classList.contains("check-col") ? 42 : 72;
        if (event.pointerId !== undefined && handle.setPointerCapture) {
          handle.setPointerCapture(event.pointerId);
        }
        document.body.classList.add("column-resizing");
        table.classList.add("is-resizing");

        const onMove = (moveEvent) => {
          const nextWidth = Math.max(minWidth, startWidth + moveEvent.clientX - startX);
          widths[index] = nextWidth;
          colgroup.children[index].style.width = `${nextWidth}px`;
          table.style.width = `${widths.reduce((sum, width) => sum + width, 0)}px`;
          table.style.minWidth = table.style.width;
        };

        const onUp = () => {
          writeStoredColumnWidths(key, widths);
          document.body.classList.remove("column-resizing");
          table.classList.remove("is-resizing");
          resizing = false;
          document.removeEventListener(eventNames.move, onMove);
          document.removeEventListener(eventNames.up, onUp);
          if (eventNames.cancel) {
            document.removeEventListener(eventNames.cancel, onUp);
          }
          try {
            handle.releasePointerCapture(event.pointerId);
          } catch (error) {
            // The browser may release capture automatically when the pointer ends.
          }
        };

        document.addEventListener(eventNames.move, onMove);
        document.addEventListener(eventNames.up, onUp);
        if (eventNames.cancel) {
          document.addEventListener(eventNames.cancel, onUp);
        }
      };

      handle.addEventListener("pointerdown", (event) => {
        startResize(event, { move: "pointermove", up: "pointerup", cancel: "pointercancel" });
      });
      handle.addEventListener("mousedown", (event) => {
        startResize(event, { move: "mousemove", up: "mouseup" });
      });
    });

    // 컨테이너 폭에 맞게 열을 확대해 우측 빈 공간을 제거한다(보이는 테이블만).
    fitTableColumns(table);
  });
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

// 점검 규칙의 기대값/실제값/상세는 하위 검사 여러 건이 " / " 로 이어 붙어
// 한 줄로 저장된다. 이를 하위 검사별로 줄바꿈해 여러 줄로 표시한다.
function escapeMultiline(value) {
  if (value === null || value === undefined || value === "") return "-";
  // " / " 구분자와 줄바꿈(\n)을 각각 한 줄로 나눠 표시한다.
  return String(value)
    .split(/ \/ |\r\n|\n/)
    .map((part) => escapeHtml(part.trim()))
    .join("<br>");
}

// 과거에 저장된 메시지에 기대값/실제값 상세가 포함되어 있어도,
// 모달의 별도 컬럼과 중복되지 않도록 메시지 컬럼에서는 원인 요약만 보여준다.
const EXPECTED_ACTUAL_MESSAGE_LINE_RE = /^(기대값|실제값)\s*[:은]/;
const ISSUE_MESSAGE_LINE_RE = /^(차이):\s*([\s\S]*)$/;

function messageWithoutExpectedActual(value) {
  return String(value || "")
    .split(/\r\n|\n/)
    .filter((line) => !EXPECTED_ACTUAL_MESSAGE_LINE_RE.test(line.trim()))
    .join("\n")
    .trim();
}

function formatIssueMessage(value) {
  if (value === null || value === undefined || value === "") return "-";
  const visibleValue = messageWithoutExpectedActual(value);
  if (!visibleValue) return "-";
  const lines = visibleValue.split(/\r\n|\n/);
  const parsedLines = lines.map((line) => {
    const match = line.match(ISSUE_MESSAGE_LINE_RE);
    return match ? { label: match[1], content: match[2] } : null;
  });
  if (!lines.length || parsedLines.some((item) => item === null)) {
    return escapeMultiline(visibleValue);
  }
  return `<div class="issue-message-grid">${parsedLines.map((item) => `
    <strong class="issue-message-label">${escapeHtml(item.label)}:</strong>
    <span class="issue-message-value">${escapeHtml(item.content)}</span>
  `).join("")}</div>`;
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

function projectsUrl() {
  const params = new URLSearchParams({
    limit: "500",
    center: state.center
  });
  return `${apiEndpoints.projects}?${params.toString()}`;
}

function jobsUrl() {
  const params = new URLSearchParams({
    status: "all",
    limit: String(jobListPageSize),
    offset: String(state.resultPagination.offset || 0)
  });
  if (state.resultJobCenter && state.resultJobCenter !== "all") {
    params.set("center", state.resultJobCenter);
  }
  return `${apiEndpoints.jobs}?${params.toString()}`;
}

async function requestJson(url, options = {}) {
  const headers = {
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
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
    credentials: "same-origin",
    referrerPolicy: "same-origin",
    ...options,
    headers
  });
  const responseText = await response.text();
  let payload = {};
  if (responseText) {
    try {
      payload = JSON.parse(responseText);
    } catch (error) {
      payload = {};
    }
  }
  if (!response.ok) {
    const error = new Error(payload.message || fallbackRequestErrorMessage(response, responseText));
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function fallbackRequestErrorMessage(response, bodyText = "") {
  const body = String(bodyText || "");
  if (response.status === 403 && /csrf|forbidden|referer/i.test(body)) {
    return "보안 토큰 확인에 실패했습니다. 페이지를 새로고침한 뒤 다시 시도해 주세요.";
  }
  if (response.status === 404) {
    return "요청 주소를 찾지 못했습니다. 페이지를 새로고침한 뒤 다시 시도해 주세요.";
  }
  if (response.status >= 500) {
    return "서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
  }
  return `요청을 처리하지 못했습니다. (HTTP ${response.status})`;
}

function normalizeReview(value) {
  const review = String(value || "").trim();
  if (!review || review === "미점검") return "미점검";
  if (review === "O") return "완료";
  if (review === "X") return "수정 필요";
  if (review === "작업실패") return "실패";
  return review;
}

function normalizeManualReviewOverride(value) {
  if (!value || !value.applied) return null;
  return {
    applied: true,
    count: Number(value.count || 1),
    memo: String(value.memo || ""),
    ruleCode: String(value.rule_code || ""),
    ruleName: String(value.rule_name || ""),
    subCheckKey: String(value.sub_check_key || ""),
    updatedAt: String(value.updated_at || "")
  };
}

function normalizeApiProject(item) {
  return {
    number: item.project_number,
    certDate: item.cert_date || "-",
    company: item.company || "",
    product: item.product || "",
    pl: item.pl || "",
    centerCode: item.center_code || state.center,
    centerLabel: item.center_label || centerLabels[item.center_code || state.center] || "",
    review: normalizeReview(item.review),
    reviewRaw: item.review_raw || item.review || "",
    reviewManualOverride: normalizeManualReviewOverride(item.review_manual_override),
    selectable: item.selectable !== false,
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

function localRuleSeed(project) {
  const digits = String(project?.number || "").replace(/\D/g, "");
  return Number(digits.slice(-5)) || 1;
}

function localInspectionRules(project) {
  if (project.rules?.length) return project.rules;
  if (project.review === "완료") {
    return makeRules(localRuleSeed(project), "complete");
  }
  if (project.review === "수정 필요") {
    return makeRules(localRuleSeed(project), "needs_fix");
  }
  return [];
}

function normalizeApiJobProject(item) {
  return {
    id: item.id,
    jobId: item.job_id,
    number: item.project_number,
    certDate: item.cert_date || "",
    company: item.company || "",
    product: item.product || "",
    centerCode: item.center_code || "",
    centerLabel: item.center_label || "",
    status: item.status,
    statusLabel: item.status_label || item.status,
    review: item.review_status_label || item.review_status || "-",
    reviewManualOverride: normalizeManualReviewOverride(item.review_manual_override),
    step: item.current_step || item.status_label || "-",
    retry: item.retry_count || 0,
    zip: item.zip_file_name || "-",
    error: item.error_message || "",
    errorDetail: item.error_detail || "",
    failStep: item.status === "failed" ? item.current_step : "",
    changeNote: item.change_note || { available: false }
  };
}

function normalizeApiJob(item) {
  return {
    id: item.id,
    displayId: formatJobIdLabel(item.id, item.requested_at),
    centerCode: item.center_code || "",
    centerLabel: item.center_label || "",
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

// 작업 ID(UUID)는 그 자체로는 날짜 등 규칙이 안 보여 언제 요청된 건지 알 수 없다.
// 실제 ID(취소/조회 API 호출용)는 그대로 두고, 화면에 보여줄 라벨만 '요청일자-짧은ID'
// 형태로 만든다.
function formatJobIdLabel(id, requestedAtIso) {
  if (!id) return "-";
  const shortId = String(id).replace(/-/g, "").slice(0, 8).toUpperCase();
  const parsed = requestedAtIso ? new Date(requestedAtIso) : null;
  if (!parsed || Number.isNaN(parsed.getTime())) return shortId;
  const y = parsed.getFullYear();
  const m = String(parsed.getMonth() + 1).padStart(2, "0");
  const d = String(parsed.getDate()).padStart(2, "0");
  return `${y}${m}${d}-${shortId}`;
}

function badge(status, options = {}) {
  const manualOverride = options.manualOverride || null;
  const manualReview = options.manualReview || null;
  const config = statusLabel[status] || [status, "badge-muted"];
  let label = config[0];
  let cls = config[1];
  let title = "";
  if (manualOverride?.applied) {
    label = "정상";
    cls = "badge-manual-pass";
    title = manualOverride.memo ? `수동 적합 사유: ${manualOverride.memo}` : "";
  } else if (manualReview?.applied) {
    cls = "badge-manual-pass";
    const count = Number(manualReview.count || 1);
    const prefix = count > 1 ? `수동 적합 ${count}건 포함 완료` : "수동 적합 포함 완료";
    title = manualReview.memo ? `${prefix}: ${manualReview.memo}` : prefix;
  }
  return `<span class="badge ${cls}"${title ? ` title="${escapeHtml(title)}"` : ""}>${escapeHtml(label)}</span>`;
}

function projectReviewBadge(item) {
  const manualReview = item?.review === "완료" ? item.reviewManualOverride : null;
  return badge(item?.review || "-", { manualReview });
}

function isProjectLocked(item) {
  return Boolean(item.activeJobId);
}

function isProjectCompleted(item) {
  return item?.review === "완료";
}

function hasInspectionResult(item) {
  // 점검이 끝난(또는 작업이 실패한) 프로젝트는 모두 상세를 볼 수 있다.
  // 완료/수정 필요 → 규칙별 점검 결과, 실패/보류 → 실패 오류 내용.
  // 미점검(이력 없음)만 비활성화한다.
  return Boolean(item.review) && item.review !== "미점검";
}

function isProjectSelectable(item) {
  return Boolean(item) && item.selectable !== false && !isProjectLocked(item) && !isProjectCompleted(item);
}

function projectWorkStatusLabel(item) {
  if (item.activeStateLabel) return item.activeStateLabel;
  if (item.review === "완료") return "완료";
  return "요청 가능";
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
  const reviews = ["전체", ...new Set(mockProjects.map((item) => item.review))];
  if (!reviews.includes(state.projectFilters.review)) {
    state.projectFilters.review = "전체";
  }
  qs("filterStatus").innerHTML = reviews.map((value) => `<option>${escapeHtml(value)}</option>`).join("");
  qs("filterStatus").value = state.projectFilters.review;
}

function resetProjectFilters() {
  state.projectFilters = defaultProjectFilters();
  ["filterProject", "filterCompany", "filterProduct", "filterPl"].forEach((id) => {
    const input = document.getElementById(id);
    if (input) input.value = "";
  });
  const status = document.getElementById("filterStatus");
  if (status) status.value = "전체";
}

function readProjectFilterInputs() {
  return {
    project: qs("filterProject").value.trim().toLowerCase(),
    company: qs("filterCompany").value.trim().toLowerCase(),
    product: qs("filterProduct").value.trim().toLowerCase(),
    pl: qs("filterPl").value.trim().toLowerCase(),
    review: qs("filterStatus").value || "전체"
  };
}

function applyProjectFilters() {
  state.projectFilters = readProjectFilterInputs();
  renderProjects();
}

function textIncludesFilter(value, filter) {
  if (!filter) return true;
  return String(value || "").toLowerCase().includes(filter);
}

async function loadProjects() {
  state.projectLoadError = "";
  qs("projectRows").innerHTML = `
    <tr><td colspan="9" class="empty-cell">프로젝트 목록을 불러오는 중입니다.</td></tr>
  `;

  try {
    const payload = await requestJson(projectsUrl());
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
  const { project, company, product, pl, review } = state.projectFilters;

  return mockProjects.filter((item) => (
    textIncludesFilter(item.number, project) &&
    textIncludesFilter(item.company, company) &&
    textIncludesFilter(item.product, product) &&
    textIncludesFilter(item.pl, pl) &&
    (review === "전체" || item.review === review)
  ));
}

function renderProjects() {
  const rows = filteredProjects();
  state.selected.forEach((number) => {
    const item = mockProjects.find((project) => project.number === number);
    if (!isProjectSelectable(item)) {
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
    const selectable = isProjectSelectable(item);
    const checked = selectable && state.selected.has(item.number) ? "checked" : "";
    const disabled = selectable ? "" : "disabled";
    const selected = state.focusedProject?.number === item.number ? "selected" : "";
    const lockedClass = selectable ? "" : "completed-locked";
    const hasDetail = hasInspectionResult(item);
    const activeLabel = projectWorkStatusLabel(item);
    const checkboxLabel = !selectable
      ? `${item.number} ${activeLabel} 상태`
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
        <td>${projectReviewBadge(item)}</td>
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
  const checkboxes = Array.from(document.querySelectorAll("[data-project-check]"));
  checkboxes.forEach((checkbox, idx) => {
    checkbox.addEventListener("click", (event) => {
      event.stopPropagation();
      const number = checkbox.dataset.projectCheck;
      const item = mockProjects.find((project) => project.number === number);
      if (!isProjectSelectable(item)) return;
      state.selectionMessage = "";

      if (event.shiftKey && state.lastCheckedIndex >= 0) {
        const lo = Math.min(state.lastCheckedIndex, idx);
        const hi = Math.max(state.lastCheckedIndex, idx);
        checkboxes.slice(lo, hi + 1).forEach((cb) => {
          if (cb.disabled) return;
          const n = cb.dataset.projectCheck;
          const it = mockProjects.find((p) => p.number === n);
          if (!isProjectSelectable(it)) return;
          state.selected.add(n);
        });
      } else {
        if (checkbox.checked) {
          state.selected.add(number);
        } else {
          state.selected.delete(number);
        }
        state.lastCheckedIndex = idx;
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

  const activeCenter = state.activeJob?.center_code || state.activeJob?.centerCode || "";
  qs("lockMessage").textContent = state.selectionMessage || (!state.hasAnyActiveJob
    ? "선택한 프로젝트는 요청 순서대로 대기열에 등록됩니다."
    : activeCenter && activeCenter !== state.center
      ? "다른 센터 작업이 진행 중입니다. 요청하면 예약됨 상태로 등록됩니다."
      : "현재 작업이 진행 중입니다. 요청하면 예약됨 상태로 등록됩니다.");
  const hasJobTarget = [...state.selected].some((number) => {
    const item = mockProjects.find((project) => project.number === number);
    return isProjectSelectable(item);
  });
  qs("requestJob").disabled = !hasJobTarget;
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
      <dt>센터</dt><dd>${escapeHtml(item.centerLabel || centerLabels[item.centerCode] || "-")}</dd>
      <dt>회사명</dt><dd>${item.company}</dd>
      <dt>제품명</dt><dd>${item.product}</dd>
      <dt>시험PL</dt><dd>${item.pl}</dd>
      <dt>점검결과</dt><dd>${projectReviewBadge(item)}</dd>
      <dt>작업상태</dt><dd>${badge(projectWorkStatusLabel(item))}</dd>
      <dt>점검날짜</dt><dd>${item.inspectionDate || "-"}</dd>
    </dl>
  `;
}

async function refreshActiveJob() {
  try {
    const payload = await requestJson(apiEndpoints.activeJob);
    state.activeJob = payload.active_job;
    state.hasAnyActiveJob = (payload.active_job_count || 0) > 0;
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
    state.hasAnyActiveJob = false;
    state.emptyJob = true;
  }
  renderProgress();
  renderSelection();
}

async function loadResultJobs(preferredJobId = null, { silent = false, resetPage = false } = {}) {
  state.resultLoadError = "";
  if (resetPage) {
    state.resultPagination.offset = 0;
  }
  if (!silent) {
    qs("jobList").innerHTML = `<p class="muted">작업 목록을 불러오는 중입니다.</p>`;
    qs("jobListPager").innerHTML = `<span class="job-page-info">작업 목록을 불러오는 중입니다.</span>`;
    qs("resultRows").innerHTML = `
      <tr><td colspan="9" class="empty-cell">작업을 불러오는 중입니다.</td></tr>
    `;
  }
  try {
    const payload = await requestJson(jobsUrl());
    state.resultJobs = payload.items.map(normalizeApiJob);
    state.resultPagination = {
      total: payload.pagination?.total || 0,
      limit: payload.pagination?.limit || jobListPageSize,
      offset: payload.pagination?.offset || 0,
      hasMore: Boolean(payload.pagination?.has_more)
    };
    state.resultJobId = preferredJobId
      || (state.resultJobs.some((job) => job.id === state.resultJobId) ? state.resultJobId : null)
      || state.resultJobs[0]?.id
      || null;
    renderJobs();
    await loadResultProjects({ silent });
  } catch (error) {
    // 폴링(silent) 중 일시적 오류는 기존 데이터를 유지한다.
    if (silent) return;
    state.resultJobs = [];
    state.resultProjects = [];
    state.resultJobId = null;
    state.resultPagination = {
      total: 0,
      limit: jobListPageSize,
      offset: 0,
      hasMore: false
    };
    state.resultLoadError = error.message;
    state.resultProjectLoadError = "";
    renderJobs();
    renderResults();
  }
}

async function loadResultProjects({ silent = false } = {}) {
  if (!state.resultJobId) {
    state.resultProjects = [];
    renderResults();
    return;
  }

  if (!silent) {
    qs("resultRows").innerHTML = `
      <tr><td colspan="9" class="empty-cell">프로젝트별 결과를 불러오는 중입니다.</td></tr>
    `;
  }

  try {
    const payload = await requestJson(`/api/jobs/${state.resultJobId}/projects/`);
    state.resultProjects = payload.items.map(normalizeApiJobProject);
    state.resultProjectLoadError = "";
    renderResults();
  } catch (error) {
    if (silent) return;
    state.resultProjects = [];
    state.resultProjectLoadError = error.message;
    renderResults();
  }
}

function renderProgress() {
  const showEmpty = state.forceEmptyPreview || !state.activeJob;
  qs("activeProgressView").hidden = showEmpty;
  qs("emptyProgressView").hidden = !showEmpty;

  if (showEmpty) {
    qs("activeJobState").innerHTML = `
      <span class="dot dot-muted"></span>
      <div><span class="label">현재 작업</span><strong>작업 없음</strong></div>
    `;
    return;
  }

  const activeJob = state.activeJob;
  const activeProjects = state.activeProjects;
  const currentProject = activeProjects.find((item) => item.status === "running") || activeProjects[0];
  const total = activeJob.requested_project_count ?? activeJob.total;
  const completed = activeJob.completed_project_count ?? activeJob.completed;
  const failed = activeJob.failed_project_count ?? activeJob.failed;
  const progressPercent = activeJob.progress_percent ?? (total ? Math.round((completed / total) * 100) : 0);

  qs("activeJobState").innerHTML = `
    <span class="dot dot-run"></span>
    <div><span class="label">현재 작업</span><strong>${activeJob.status_label || "진행 중"}</strong></div>
  `;
  qs("jobId").textContent = formatJobIdLabel(activeJob.id, activeJob.requested_at);
  qs("jobProgress").textContent = `${completed} / ${total}`;
  qs("currentProject").textContent = currentProject?.number || "-";
  qs("failedCount").textContent = `${failed}건`;
  qs("currentStep").textContent = activeJob.progress_message || currentProject?.step || "-";
  qs("progressBar").style.width = `${progressPercent}%`;

  const worker = {
    ...(activeJob.worker || {}),
    stale: state.heartbeatWarning,
    heartbeat: state.heartbeatWarning ? null : (activeJob.worker?.heartbeat_at || null)
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
      <td>
        <button class="mini-button" type="button" data-progress-rule-result="${escapeHtml(item.id)}">
          상세
        </button>
      </td>
      <td>${item.error ? `<button class="link-button" type="button" data-error-detail="progress:${escapeHtml(item.id || item.number)}">${escapeHtml(item.error)}</button>` : "-"}</td>
    </tr>
  `).join("") : `
    <tr><td colspan="9" class="empty-cell">작업은 있지만 현재 작업의 프로젝트 정보가 아직 없습니다.</td></tr>
  `;

  bindProgressRuleResultButtons();
  bindErrorButtons();
}

function renderJobCenterTabs() {
  document.querySelectorAll("[data-job-center-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.jobCenterTab === state.resultJobCenter);
  });
}

function renderJobPagination() {
  const pager = qs("jobListPager");
  if (!pager) return;

  const total = state.resultPagination.total || 0;
  const limit = state.resultPagination.limit || jobListPageSize;
  const offset = state.resultPagination.offset || 0;
  const page = total ? Math.floor(offset / limit) + 1 : 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const start = total ? offset + 1 : 0;
  const end = total ? Math.min(offset + state.resultJobs.length, total) : 0;

  pager.innerHTML = `
    <span class="job-page-info">
      <i class="fa-solid fa-list-check" aria-hidden="true"></i>
      <span>${start}-${end} / ${total} · ${page}/${totalPages}페이지</span>
    </span>
    <div class="job-page-actions">
      <button class="mini-button job-page-button" type="button" data-job-page="prev" aria-label="이전 작업 페이지" ${offset <= 0 ? "disabled" : ""}>
        <i class="fa-solid fa-chevron-left" aria-hidden="true"></i>
        <span>이전</span>
      </button>
      <button class="mini-button job-page-button" type="button" data-job-page="next" aria-label="다음 작업 페이지" ${!state.resultPagination.hasMore ? "disabled" : ""}>
        <span>다음</span>
        <i class="fa-solid fa-chevron-right" aria-hidden="true"></i>
      </button>
    </div>
  `;
}

function renderJobs() {
  renderJobCenterTabs();
  renderJobPagination();

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
        <span>${escapeHtml(job.displayId)}</span>
        <span>${badge(job.centerLabel || centerLabels[job.centerCode] || "-")} ${badge(job.statusLabel || job.status)}</span>
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
  const downloadButton = qs("downloadJobResults");
  if (downloadButton) {
    downloadButton.disabled = !job;
  }

  if (!job) {
    qs("resultCaption").textContent = "작업을 선택하면 프로젝트별 결과를 표시합니다.";
    qs("resultRows").innerHTML = `
      <tr><td colspan="9" class="empty-cell">${state.resultLoadError ? escapeHtml(state.resultLoadError) : "조회된 작업이 없습니다."}</td></tr>
    `;
    return;
  }

  qs("resultCaption").textContent = `${job.displayId} · 완료 ${job.success}건 · 실패 ${job.failed}건`;

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
      <td>${projectReviewBadge(item)}</td>
      <td>
        <button class="mini-button" type="button" data-rule-result="${escapeHtml(item.id)}">
          상세
        </button>
      </td>
      <td>${escapeHtml(item.step || "-")}</td>
      <td>${escapeHtml(item.failStep || "-")}</td>
      <td>${item.error ? `<button class="link-button" type="button" data-error-detail="result:${escapeHtml(item.id)}">${escapeHtml(item.error)}</button>` : "-"}</td>
    </tr>
  `).join("");

  bindRuleResultButtons();
  bindErrorButtons();
}

function openModal({ eyebrow, title, body, downloadName = "" }) {
  qs("modalEyebrow").textContent = eyebrow;
  qs("modalTitle").textContent = title;
  qs("modalBody").innerHTML = body;
  setModalDownload(downloadName);
  setModalFullFolderDownload(null);
  setModalChangeNote(null, null);
  qs("detailModal").hidden = false;
}

function closeModal() {
  qs("detailModal").hidden = true;
  setModalDownload("");
  setModalFullFolderDownload(null);
  setModalChangeNote(null, null);
}

function safeDownloadFilename(value) {
  const fallback = "download-review-popup";
  const cleaned = String(value || fallback)
    .replace(/[\\/:*?"<>|]+/g, "_")
    .replace(/\s+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
  const filename = cleaned || fallback;
  return filename.toLowerCase().endsWith(".html") ? filename : `${filename}.html`;
}

function setModalDownload(filename) {
  const link = qs("modalDownload");
  if (!link) return;

  state.modalDownloadFilename = filename ? safeDownloadFilename(filename) : "";
  link.href = "#";

  if (state.modalDownloadFilename) {
    link.hidden = false;
    return;
  }
  link.hidden = true;
}

function setModalFullFolderDownload(project) {
  const button = qs("modalFullFolderDownload");
  if (!button) return;

  if (!project?.number) {
    state.modalFullFolderProject = null;
    button.hidden = true;
    button.disabled = false;
    button.innerHTML = `<i class="fa-solid fa-folder" aria-hidden="true"></i> 전체 산출물 다운로드`;
    button.removeAttribute("title");
    return;
  }

  state.modalFullFolderProject = {
    number: project.number,
    certDate: project.certDate || ""
  };
  button.hidden = false;
  button.disabled = false;
  button.title = "시험 이력 조회의 전체 문서 다운로드와 동일하게 ECM 전체 산출물을 다운로드합니다.";
  button.innerHTML = `<i class="fa-solid fa-folder" aria-hidden="true"></i> 전체 산출물 다운로드`;
}

function setModalChangeNote(project, note) {
  const button = qs("modalChangeNote");
  if (!button) return;

  const available = Boolean(note?.available);
  if (!project?.id || !available) {
    state.modalChangeNoteProject = null;
    button.disabled = true;
    button.title = "ECM에서 파일명에 '수정'이 포함된 txt 파일이 발견되면 활성화됩니다.";
    button.innerHTML = `<i class="fa-solid fa-file-lines"></i> 수정 내용`;
    return;
  }

  state.modalChangeNoteProject = {
    id: project.id,
    number: project.number || "",
    fileName: note.file_name || "수정 관련 txt 파일"
  };
  button.disabled = false;
  button.title = `${state.modalChangeNoteProject.fileName} 내용을 확인합니다.`;
  button.innerHTML = `<i class="fa-solid fa-file-lines"></i> 수정 내용`;
}

function openChangeNotePopup(note, project) {
  const title = `${project?.number || ""} ${note.file_name || "수정 관련 txt 파일"}`.trim();
  qs("changeNoteTitle").textContent = title || "수정 관련 txt 파일";
  qs("changeNoteContent").textContent = note.content || "(내용 없음)";
  qs("changeNoteModal").hidden = false;
}

function closeChangeNotePopup() {
  qs("changeNoteModal").hidden = true;
  qs("changeNoteContent").textContent = "";
}

function openManualPassPopup(item) {
  state.manualOverrideTarget = {
    id: item.id,
    subCheckKey: item.sub_check_key || "",
    ruleName: item.rule_name || "-",
    displayNumber: item.display_number || item.sequence || ""
  };
  qs("manualOverrideTitle").textContent = "수동 적합 처리";
  qs("manualOverrideRuleName").textContent = [
    state.manualOverrideTarget.displayNumber,
    state.manualOverrideTarget.ruleName
  ].filter(Boolean).join(" ");
  qs("manualOverrideMemo").value = "";
  qs("manualOverrideMemo").readOnly = false;
  qs("manualOverrideError").hidden = true;
  qs("confirmManualOverride").hidden = false;
  qs("confirmManualOverride").disabled = false;
  qs("confirmManualOverride").textContent = "적합으로 변경";
  qs("cancelManualOverride").textContent = "취소";
  qs("manualOverrideModal").hidden = false;
  setTimeout(() => qs("manualOverrideMemo").focus(), 0);
}

function openManualPassNotePopup(item) {
  const manualOverride = manualOverrideOf(item);
  if (!manualOverride) return;
  state.manualOverrideTarget = null;
  qs("manualOverrideTitle").textContent = "수동 적합 메모";
  qs("manualOverrideRuleName").textContent = [
    item.display_number || item.sequence || "",
    item.rule_name || manualOverride.rule_name || "-"
  ].filter(Boolean).join(" ");
  qs("manualOverrideMemo").value = manualOverride.memo || "";
  qs("manualOverrideMemo").readOnly = true;
  qs("manualOverrideError").hidden = true;
  qs("confirmManualOverride").hidden = true;
  qs("confirmManualOverride").textContent = "적합으로 변경";
  qs("cancelManualOverride").textContent = "닫기";
  qs("manualOverrideModal").hidden = false;
}

function closeManualPassPopup() {
  qs("manualOverrideModal").hidden = true;
  qs("manualOverrideMemo").value = "";
  qs("manualOverrideMemo").readOnly = false;
  qs("manualOverrideError").hidden = true;
  qs("confirmManualOverride").hidden = false;
  qs("confirmManualOverride").textContent = "적합으로 변경";
  state.manualOverrideTarget = null;
}

async function confirmManualPassOverride() {
  const target = state.manualOverrideTarget;
  if (!target?.id) return;
  const memo = qs("manualOverrideMemo").value.trim();
  if (!memo) {
    qs("manualOverrideError").textContent = "수동 적합 처리 사유를 입력해야 합니다.";
    qs("manualOverrideError").hidden = false;
    qs("manualOverrideMemo").focus();
    return;
  }

  const button = qs("confirmManualOverride");
  button.disabled = true;
  button.textContent = "저장 중";
  try {
    const payload = await requestJson(`/api/rule-results/${encodeURIComponent(target.id)}/manual-pass/`, {
      method: "POST",
      body: JSON.stringify({ memo, sub_check_key: target.subCheckKey || "" })
    });
    closeManualPassPopup();
    updateInspectionModalFromPayload(payload);
    await Promise.allSettled([
      loadProjects(),
      state.resultJobId ? loadResultProjects({ silent: true }) : Promise.resolve()
    ]);
  } catch (error) {
    qs("manualOverrideError").textContent = error.message || "수동 적합 처리에 실패했습니다.";
    qs("manualOverrideError").hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "적합으로 변경";
  }
}

async function openPlAssignmentModal() {
  qs("plAssignmentError").hidden = true;
  qs("plAssignmentError").textContent = "";
  qs("plAssignmentModal").hidden = false;
  ["left", "right"].forEach((side) => {
    const list = document.querySelector(`[data-pl-list="${side}"]`);
    if (list) list.innerHTML = `<li class="pl-assignment-list-empty">불러오는 중입니다...</li>`;
  });

  try {
    const payload = await requestJson(apiEndpoints.plAssignments);
    plAssignData = payload;
    plAssignCountByName = {};
    plAssignOriginalCenterByName = {};
    plAssignCurrentCenterByName = {};
    Object.entries(payload.assignments || {}).forEach(([code, items]) => {
      (items || []).forEach((item) => {
        plAssignCountByName[item.name] = item.project_count;
        plAssignOriginalCenterByName[item.name] = code;
        plAssignCurrentCenterByName[item.name] = code;
      });
    });

    const centers = payload.centers || [];
    const firstRealCenter = centers.find((center) => center.code !== "unknown");
    plAssignActiveTab = {
      left: firstRealCenter?.code || centers[0]?.code || "",
      right: "unknown"
    };
    plAssignSelected = { left: new Set(), right: new Set() };
    renderPlAssignmentSide("left");
    renderPlAssignmentSide("right");
  } catch (error) {
    qs("plAssignmentError").textContent = error.message || "PL 배정 목록을 불러오지 못했습니다.";
    qs("plAssignmentError").hidden = false;
  }
}

function closePlAssignmentModal() {
  qs("plAssignmentModal").hidden = true;
  plAssignData = null;
  plAssignCountByName = {};
  plAssignOriginalCenterByName = {};
  plAssignCurrentCenterByName = {};
  plAssignSelected = { left: new Set(), right: new Set() };
}

function renderPlAssignmentSide(side) {
  renderPlAssignmentTabs(side);
  renderPlAssignmentList(side);
}

function renderPlAssignmentTabs(side) {
  const nav = document.querySelector(`[data-pl-tabs="${side}"]`);
  if (!nav || !plAssignData) return;
  nav.innerHTML = (plAssignData.centers || []).map((center) => {
    const active = plAssignActiveTab[side] === center.code;
    return `<button class="center-tab-button${active ? " active" : ""}" type="button" data-pl-tab-code="${escapeHtml(center.code)}">${escapeHtml(center.label)}</button>`;
  }).join("");
  nav.querySelectorAll("[data-pl-tab-code]").forEach((button) => {
    button.addEventListener("click", () => {
      plAssignActiveTab[side] = button.dataset.plTabCode;
      plAssignSelected[side].clear();
      renderPlAssignmentSide(side);
    });
  });
}

function plAssignNamesForCenter(code) {
  return Object.keys(plAssignCurrentCenterByName)
    .filter((name) => plAssignCurrentCenterByName[name] === code)
    .sort((a, b) => (plAssignCountByName[b] || 0) - (plAssignCountByName[a] || 0) || a.localeCompare(b, "ko"));
}

function renderPlAssignmentList(side) {
  const list = document.querySelector(`[data-pl-list="${side}"]`);
  if (!list) return;
  const names = plAssignNamesForCenter(plAssignActiveTab[side]);
  if (!names.length) {
    list.innerHTML = `<li class="pl-assignment-list-empty">배정된 PL이 없습니다.</li>`;
    return;
  }
  list.innerHTML = names.map((name) => {
    const selected = plAssignSelected[side].has(name);
    const count = plAssignCountByName[name] || 0;
    return `<li class="pl-assignment-list-item${selected ? " selected" : ""}" data-pl-name="${escapeHtml(name)}">
      <span>${escapeHtml(name)}</span>
      <span class="pl-assignment-count">${count}개</span>
    </li>`;
  }).join("");
  list.querySelectorAll("[data-pl-name]").forEach((item) => {
    item.addEventListener("click", () => {
      const name = item.dataset.plName;
      if (plAssignSelected[side].has(name)) {
        plAssignSelected[side].delete(name);
      } else {
        plAssignSelected[side].add(name);
      }
      renderPlAssignmentList(side);
    });
  });
}

function movePlAssignmentSelection(fromSide, toSide) {
  const targetCenter = plAssignActiveTab[toSide];
  const selectedNames = [...plAssignSelected[fromSide]];
  if (!targetCenter || !selectedNames.length) return;
  selectedNames.forEach((name) => {
    plAssignCurrentCenterByName[name] = targetCenter;
  });
  plAssignSelected[fromSide].clear();
  renderPlAssignmentList("left");
  renderPlAssignmentList("right");
}

async function confirmPlAssignmentChanges() {
  const changes = [];
  Object.keys(plAssignCurrentCenterByName).forEach((name) => {
    const fromCenter = plAssignOriginalCenterByName[name];
    const toCenter = plAssignCurrentCenterByName[name];
    if (fromCenter !== toCenter) {
      changes.push({ name, from_center: fromCenter, to_center: toCenter });
    }
  });
  if (!changes.length) {
    closePlAssignmentModal();
    return;
  }

  const button = qs("confirmPlAssignment");
  button.disabled = true;
  button.textContent = "적용 중";
  try {
    await requestJson(apiEndpoints.plAssignmentsApply, {
      method: "POST",
      body: JSON.stringify({ changes })
    });
    closePlAssignmentModal();
    resetProjectFilters();
    await loadProjects();
  } catch (error) {
    qs("plAssignmentError").textContent = error.message || "PL 배정 적용에 실패했습니다.";
    qs("plAssignmentError").hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "확인";
  }
}

function updateInspectionModalFromPayload(payload) {
  const payloadProject = payload.project ? normalizeApiJobProject(payload.project) : {};
  const projectNumber = payloadProject.number || qs("modalTitle").textContent.replace(" 규칙별 점검 결과", "");
  const rawItems = Array.isArray(payload.items) ? payload.items : [];
  const displayItems = Array.isArray(payload.display_items) ? payload.display_items : rawItems;
  const previousFilter = state.inspectionFilter;
  qs("modalTitle").textContent = `${projectNumber} 규칙별 점검 결과`;
  setModalDownload(`${projectNumber}_규칙별_점검_결과.html`);
  setModalFullFolderDownload({
    id: payloadProject.id,
    number: projectNumber,
    certDate: payloadProject.certDate || ""
  });
  setModalChangeNote(
    { id: payloadProject.id, number: projectNumber },
    payloadProject.changeNote
  );
  mountInspectionResult(
    displayItems,
    `작업 프로젝트 ${projectNumber}의 규칙 결과입니다.`,
    { ruleItems: rawItems }
  );
  state.inspectionFilter = previousFilter;
  refreshInspectionTable();
}

function triggerAttachmentDownload(url) {
  const anchor = document.createElement("a");
  anchor.href = url;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function fullProjectFolderDownloadUrl(project) {
  const params = new URLSearchParams();
  if (project?.certDate) params.set("cert_date", project.certDate);
  if (state.center) params.set("center", state.center);
  const query = params.toString();
  const base = `/api/projects/${encodeURIComponent(project.number)}/full-documents-download/`;
  return query ? `${base}?${query}` : base;
}

function startFullProjectFolderDownload(project) {
  // 전체 산출물 다운로드를 재사용할 때는 이 헬퍼를 사용한다.
  // fetch/POST로 준비 완료 JSON을 기다리면 브라우저 다운로드 시작이 늦어진다.
  triggerAttachmentDownload(fullProjectFolderDownloadUrl(project));
}
function collectDownloadStyles() {
  const styles = [];
  Array.from(document.styleSheets).forEach((sheet) => {
    try {
      const rules = Array.from(sheet.cssRules || []).map((rule) => rule.cssText).join("\n");
      if (rules) styles.push(rules);
    } catch (error) {
      // Cross-origin stylesheets can be skipped; the export keeps local layout CSS.
    }
  });
  styles.push(`
    body { margin: 0; padding: 24px; background: #f4f6f8; color: #1f2937; font-family: "Malgun Gothic", "Noto Sans KR", "Segoe UI", Arial, sans-serif; }
    .download-export { max-width: 1280px; margin: 0 auto; }
    .download-export .modal-panel { width: auto; height: auto; min-width: 0; min-height: 0; max-width: none; max-height: none; overflow: visible; resize: none; box-shadow: none; }
    .download-export .modal-body { max-height: none; overflow: visible; }
    .download-export .inspection-result-shell { min-height: 0; }
    .download-export .inspection-result-table { max-height: none; overflow: visible; }
  `);
  return styles.join("\n");
}

function modalHtmlForDownload() {
  const panel = qs("detailModal")?.querySelector(".modal-panel");
  if (!panel) return "";

  const clone = panel.cloneNode(true);
  clone.querySelector(".modal-header-actions")?.remove();
  clone.querySelectorAll(".help-panel").forEach((help) => help.remove());
  clone.querySelectorAll("a[href]").forEach((link) => {
    const href = link.getAttribute("href");
    if (href && href !== "#") {
      link.setAttribute("href", new URL(href, window.location.href).toString());
    }
  });

  const title = qs("modalTitle")?.textContent?.trim() || "규칙별 점검 결과";
  return `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>${escapeHtml(title)}</title>
  <style>${collectDownloadStyles()}</style>
</head>
<body>
  <main class="download-review-page download-export">
    ${clone.outerHTML}
  </main>
</body>
</html>`;
}

function downloadCurrentModalHtml(event) {
  event?.preventDefault();
  if (!state.modalDownloadFilename || qs("detailModal").hidden) return;

  const html = modalHtmlForDownload();
  if (!html) return;

  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = state.modalDownloadFilename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function downloadCurrentProjectFullFolder(event) {
  event?.preventDefault();
  const project = state.modalFullFolderProject;
  const button = qs("modalFullFolderDownload");
  if (!project?.number || !button || button.disabled) return;

  button.disabled = true;
  button.innerHTML = `<i class="fa-solid fa-folder" aria-hidden="true"></i> 다운로드 시작`;
  startFullProjectFolderDownload(project);
  window.setTimeout(() => {
    if (state.modalFullFolderProject?.number === project.number) {
      button.disabled = false;
      button.innerHTML = `<i class="fa-solid fa-folder" aria-hidden="true"></i> 전체 산출물 다운로드`;
    }
  }, 1500);
}

async function openCurrentProjectChangeNote(event) {
  event?.preventDefault();
  const project = state.modalChangeNoteProject;
  const button = qs("modalChangeNote");
  if (!project?.id || !button || button.disabled) return;

  button.disabled = true;
  button.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> 불러오는 중`;
  try {
    const payload = await requestJson(
      `/api/job-projects/${encodeURIComponent(project.id)}/change-note/`
    );
    openChangeNotePopup(payload.change_note || {}, project);
  } catch (error) {
    alert(`수정 내용 조회 실패: ${error.message}`);
  } finally {
    if (state.modalChangeNoteProject?.id === project.id) {
      button.disabled = false;
      button.innerHTML = `<i class="fa-solid fa-file-lines"></i> 수정 내용`;
    }
  }
}

function downloadJobResults() {
  if (!state.resultJobId) return;
  window.location.href = `/api/jobs/${encodeURIComponent(state.resultJobId)}/results.xlsx`;
}

function bulkDownloadSelected() {
  const downloadable = [...state.selected].filter((number) => {
    const item = mockProjects.find((project) => project.number === number);
    return item && hasInspectionResult(item) && item.review !== "보류";
  });

  if (!downloadable.length) {
    openModal({
      eyebrow: "일괄 다운로드",
      title: "다운로드할 항목 없음",
      body: `
        <div class="modal-message warning">
          <strong>점검 결과(완료·수정 필요)가 있는 항목이 선택되지 않았습니다.</strong>
          <p>목록에서 완료 또는 수정 필요 상태의 프로젝트를 선택한 뒤 다시 시도하세요.</p>
        </div>
      `
    });
    return;
  }

  const params = new URLSearchParams({ center: state.center });
  downloadable.forEach((number) => params.append("pn", number));
  window.location.href = `/api/projects/bulk-download/?${params.toString()}`;
}

function openRequestCompleteModal(payload, requestedCount) {
  openModal({
    eyebrow: "작업 요청",
    title: "작업 요청 완료",
    body: `
      <div class="modal-message success">
        <strong>${escapeHtml(payload.message || "작업 요청이 등록되었습니다.")}</strong>
        <p>요청 프로젝트 ${requestedCount}건 · 작업 ID ${escapeHtml(formatJobIdLabel(payload.job_id, payload.requested_at))}</p>
        <p>현재 상태: ${escapeHtml(payload.status_label || payload.status || "-")}</p>
      </div>
    `
  });
}

function openCancelJobModal(job) {
  openModal({
    eyebrow: "예약 취소",
    title: `${job.displayId} 작업 취소`,
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

function openForceStopModal() {
  openModal({
    eyebrow: "강제 종료",
    title: "진행중 작업 강제 종료",
    body: `
      <div class="modal-message warning">
        <strong>진행중(실행 중 포함) 작업을 강제로 종료하고 워커 락을 해제합니다.</strong>
        <p>워커가 비정상 종료되어 작업이 멈춘 채 새 작업을 시작할 수 없을 때 사용하세요.
        먼저 워커가 실제로 실행 중이라면 서버에서 워커를 중지(stop_worker)한 뒤 실행하는 것을 권장합니다.</p>
        <p>강제 종료된 프로젝트는 프로젝트 선택 탭에서 다시 요청할 수 있습니다.</p>
      </div>
      <div class="modal-actions">
        <button class="secondary-button" type="button" data-close-force-modal>닫기</button>
        <button class="primary-button danger-action" type="button" data-confirm-force-stop>강제 종료 실행</button>
      </div>
    `
  });
  qs("modalBody").querySelector("[data-close-force-modal]").addEventListener("click", closeModal);
  qs("modalBody").querySelector("[data-confirm-force-stop]").addEventListener("click", forceStopActiveJob);
}

async function forceStopActiveJob() {
  const button = qs("modalBody").querySelector("[data-confirm-force-stop]");
  if (button) {
    button.disabled = true;
    button.textContent = "강제 종료 중";
  }

  try {
    const payload = await requestJson(apiEndpoints.jobsForceStop, { method: "POST" });
    openModal({
      eyebrow: "강제 종료",
      title: "강제 종료 완료",
      body: `
        <div class="modal-message success">
          <strong>${escapeHtml(payload.message || "진행중 작업을 강제 종료했습니다.")}</strong>
          <p>이제 새 작업을 요청할 수 있습니다.</p>
        </div>
      `
    });
    await Promise.allSettled([
      refreshActiveJob(),
      loadProjects(),
      loadResultJobs()
    ]);
  } catch (error) {
    openModal({
      eyebrow: "강제 종료",
      title: "강제 종료 실패",
      body: `
        <div class="modal-message warning">
          <strong>${escapeHtml(error.message)}</strong>
        </div>
      `
    });
  }
}

async function openInspectionModal(projectNumber) {
  const project = mockProjects.find((item) => item.number === projectNumber);
  if (!project) return;

  openModal({
    eyebrow: "점검 결과",
    title: `${project.number} 규칙별 점검 결과`,
    body: `${renderInspectionModalHelp()}<p class="modal-lead">최근 점검 결과를 불러오는 중입니다.</p>`
  });
  setModalFullFolderDownload(project);

  try {
    const params = new URLSearchParams({ center: state.center });
    const payload = await requestJson(`/api/projects/${encodeURIComponent(projectNumber)}/latest-results/?${params.toString()}`);
    renderLatestInspectionResult(payload);
  } catch (error) {
    if (error.payload?.error_code === "not_found") {
      qs("modalBody").innerHTML = `
        ${renderInspectionModalHelp()}
        <div class="modal-message">
          <p>아직 이 프로젝트의 점검 이력이 없습니다. 프로젝트를 선택하고 점검을 시작하세요.</p>
        </div>
      `;
    } else {
      renderLocalInspectionFallback(project, error);
    }
  }
}

function renderLocalInspectionFallback(project, error) {
  if (project.review === "보류") {
    qs("modalBody").innerHTML = `
      ${renderInspectionModalHelp()}
      <div class="modal-message warning">
        <strong>${escapeHtml(project.holdReason || "작업 자체가 실패하여 보류되었습니다.")}</strong>
        <p>작업 자체가 실패했기 때문에 점검 규칙 결과는 생성되지 않았습니다. 원인을 확인한 뒤 다시 작업을 요청해야 합니다.</p>
      </div>
    `;
    return;
  }

  const fallbackRules = localInspectionRules(project);
  if (fallbackRules.length) {
    const rows = fallbackRules.map((rule) => `
      <tr>
        <td>${rule.no}</td>
        <td>${escapeHtml(rule.name)}</td>
        <td>${badge(rule.status)}</td>
        <td>${escapeHtml(rule.detail)}</td>
      </tr>
    `).join("");

    qs("modalBody").innerHTML = `
      ${renderInspectionModalHelp()}
      <p class="modal-lead">${project.rules.length
        ? "약 30개 점검 규칙을 표로 확인하는 화면입니다. 실제 규칙 정의 후 컬럼은 확장할 수 있습니다."
        : "최근 작업 이력이 없는 완료/수정 필요 프로젝트라 더미 규칙 결과를 표시합니다."}</p>
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
    `;
    return;
  }

  qs("modalBody").innerHTML = `
    ${renderInspectionModalHelp()}
    <div class="modal-message warning">
      <strong>${escapeHtml(error.message || "점검 이력을 찾을 수 없습니다.")}</strong>
      <p>이 프로젝트에 연결된 완료/실패 작업 이력이 아직 없거나 규칙 결과가 생성되지 않았습니다.</p>
    </div>
  `;
}

function renderLatestInspectionResult(payload) {
  const project = normalizeApiJobProject(payload.project);
  if (project.id) {
    setModalDownload(`${project.number || project.id}_규칙별_점검_결과.html`);
    setModalFullFolderDownload(project);
    setModalChangeNote(project, project.changeNote);
  }

  const rawItems = Array.isArray(payload.items) ? payload.items : [];
  if (!rawItems.length) {
    // 작업이 실패해 규칙 결과가 없는 경우: 작업 조회 탭의 '오류' 값(error_message)과
    // 상세 내용을 그대로 상세 모달에 표시한다.
    const titleEl = qs("modalTitle");
    if (titleEl) titleEl.textContent = `${project.number} 실패 상세`;
    const eyebrowEl = qs("modalEyebrow");
    if (eyebrowEl) eyebrowEl.textContent = "오류 상세";
    qs("modalBody").innerHTML = `
      ${renderInspectionModalHelp()}
      <div class="modal-message warning">
        <strong>${escapeHtml(project.error || "작업이 실패하여 점검 규칙 결과가 생성되지 않았습니다.")}</strong>
        <dl class="error-detail-list">
          <dt>상태</dt><dd>${badge(project.statusLabel || project.status)}</dd>
          <dt>실패 단계</dt><dd>${escapeHtml(project.failStep || project.step || "-")}</dd>
          <dt>오류 요약</dt><dd>${escapeHtml(project.error || "-")}</dd>
          <dt>상세 내용</dt><dd>${escapeHtml(project.errorDetail || "상세 로그가 없습니다.")}</dd>
          <dt>최근 작업</dt><dd>${escapeHtml(payload.job?.id || "-")}</dd>
        </dl>
      </div>
    `;
    return;
  }

  const displayItems = Array.isArray(payload.display_items) ? payload.display_items : rawItems;

  mountInspectionResult(
    displayItems,
    `최근 작업 ${payload.job?.id || "-"}의 규칙 결과입니다.`,
    { ruleItems: rawItems }
  );
}

function renderRuleArtifacts(rule) {
  const artifacts = Array.isArray(rule?.artifacts) ? rule.artifacts : [];
  if (!artifacts.length) return "-";

  return artifacts.map((artifact) => {
    const resultId = encodeURIComponent(rule.id || "");
    const artifactId = encodeURIComponent(artifact.id || "");
    const href = `/api/rule-results/${resultId}/artifacts/${artifactId}/`;
    const label = artifact.label || (artifact.download ? "다운로드" : "보기");
    return `<a class="mini-button" href="${href}" target="_blank" rel="noopener">${escapeHtml(label)}</a>`;
  }).join(" ");
}

function friendlyExpected(rule) {
  const expected = String(rule?.expected || "").trim();
  if (!expected) return "-";

  const normalized = expected.replace(/\s+/g, " ");
  const quotedText = normalized.match(/'([^']+)'/);
  const fileCount = normalized.match(/(.+?) 파일 (\d+)개/);
  const minCount = normalized.match(/(.+?) (\d+)개 이상/);
  const cellEquals = normalized.match(/(.+?) 오른쪽 셀 = (.+)/);
  const contains = normalized.match(/문서에 '([^']+)' 포함|문서 내 '([^']+)' 포함/);

  if (normalized === "다운로드 산출물 저장 가능") {
    return "다운로드된 산출물을 열어 점검할 수 있어야 합니다.";
  }
  if (normalized === "모든 파일 크기 1 byte 이상") {
    return "빈 파일 없이 실제 내용이 있는 파일이어야 합니다.";
  }
  if (normalized === "Word 파일 1개 / PDF 파일 1개") {
    return "Word 파일 1개와 PDF 파일 1개가 있으면 됩니다.";
  }
  if (normalized.includes("Word/PDF 파싱 가능")) {
    return "Word/PDF 파일을 열어 필요한 내용을 읽을 수 있어야 합니다.";
  }
  if (normalized.includes("Word 파일 표")) {
    return "Word 파일 안에 필요한 표가 있어야 합니다.";
  }
  if (normalized.includes("파일명에") && normalized.includes("포함")) {
    return `${normalized.replace("파일명에 ", "")}하도록 파일명이 작성되어야 합니다.`;
  }
  if (fileCount) {
    return `${fileCount[1]} 파일이 ${fileCount[2]}개 있어야 합니다.`;
  }
  if (minCount) {
    return `${minCount[1]}이 최소 ${minCount[2]}개 있어야 합니다.`;
  }
  if (normalized.includes("파싱 가능")) {
    return "파일을 열어 필요한 내용을 읽을 수 있어야 합니다.";
  }
  if (normalized.startsWith("시트 1개")) {
    return `엑셀 시트 구성과 주요 표기값이 기준과 맞아야 합니다. (${normalized})`;
  }
  if (cellEquals) {
    return `${cellEquals[1]} 항목의 오른쪽 셀 값이 ${cellEquals[2]}이어야 합니다.`;
  }
  if (contains) {
    return `문서 본문에 '${contains[1] || contains[2]}' 문구가 있어야 합니다.`;
  }
  if (quotedText && normalized.includes("포함")) {
    return `점검 위치에 '${quotedText[1]}' 문구가 표시되어야 합니다.`;
  }
  if (normalized.includes("~") && (normalized.includes("시작일") || normalized.includes("종료일") || normalized.includes("시험기간"))) {
    return `시험기간 또는 수정일자가 기준 기간과 일치해야 합니다. (${normalized})`;
  }
  if (normalized.includes("산출 변수")) {
    return "앞 단계에서 추출한 기준값을 사용할 수 있어야 합니다.";
  }
  if (normalized.includes("값 동일")) {
    return "서로 비교하는 표의 값이 동일해야 합니다.";
  }
  return normalized;
}

// 기대값/실제값 등 " / " 로 이어진 문자열을 하위 검사 단위로 분해한다.
function splitSlash(value) {
  if (value === null || value === undefined || value === "") return [];
  return String(value).split(" / ").map((part) => part.trim());
}

// 규칙 결과를 하위 검사 행 목록으로 분해한다.
// 반환: [{expected, actual, message, passed}] — passed는 boolean(행별 배지 가능) 또는 null(전체 배지 사용).
// 분해 결과가 1행 이하이면 빈 배열을 반환해 호출부가 단일 행으로 렌더링하도록 한다.
function ruleSubChecks(rule) {
  const rd = rule.raw_detail || {};

  // 1) 백엔드가 명시적으로 sub_checks를 제공하면 그대로 사용한다(각 {expected, actual, passed, message}).
  //    결함리포트(차시별), 시험계획서(항목별) 등이 여기에 해당.
  if (Array.isArray(rd.sub_checks) && rd.sub_checks.length) {
    return rd.sub_checks.map((sub, index) => ({
      expected: sub.expected !== undefined && sub.expected !== null && sub.expected !== "" ? String(sub.expected) : "-",
      actual: sub.actual !== undefined && sub.actual !== null && sub.actual !== "" ? String(sub.actual) : "-",
      message: sub.message !== undefined && sub.message !== null && sub.message !== "" ? String(sub.message) : "",
      passed: typeof sub.passed === "boolean" ? sub.passed : null,
      sub_check_key: sub.sub_check_key || sub.key || `sub-${index + 1}`,
      manual_override: sub.manual_override && sub.manual_override.applied ? sub.manual_override : null,
    }));
  }

  // 2) 폴백: expected/actual를 " / " 로 분해. document_artifact_check는 file/content_checks로 행별 배지.
  const expParts = splitSlash(rule.expected);
  const actParts = splitSlash(rule.actual);
  const rowCount = Math.max(expParts.length, actParts.length);
  if (rowCount <= 1) return [];

  const fileChecks = Array.isArray(rd.file_checks) ? rd.file_checks : [];
  const contentChecks = Array.isArray(rd.content_checks) ? rd.content_checks : [];
  const flags = [...fileChecks, ...contentChecks]
    .map((c) => (typeof c.passed === "boolean" ? c.passed : null));
  const usePerRow = flags.length === rowCount && flags.every((f) => f !== null);

  const rows = [];
  for (let i = 0; i < rowCount; i += 1) {
    rows.push({
      expected: expParts[i] !== undefined ? expParts[i] : "-",
      actual: actParts[i] !== undefined ? actParts[i] : "-",
      message: "",
      passed: usePerRow ? flags[i] : null,
      sub_check_key: `sub-${i + 1}`,
    });
  }
  return rows;
}

function manualOverrideOf(item) {
  const value = item?.manual_override;
  return value && value.applied ? value : null;
}

function isPassStatusValue(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return ["정상", "완료", "pass", "passed", "success", "ok", "o"].includes(normalized);
}

function inspectionStatusType(rule) {
  const value = String(rule?.status_label || rule?.status || "").trim().toLowerCase();
  if (["정상", "완료", "pass", "passed", "success", "ok", "o"].includes(value)) return "success";
  if (value.includes("부적합") || value.includes("오류") || value.includes("실패") || value.includes("fail") || value === "x") return "danger";
  if (value.includes("보류") || value.includes("경고") || value.includes("확인") || value.includes("warn")) return "warning";
  return "muted";
}

function inspectionSummary(items) {
  return items.reduce((summary, item) => {
    summary.total += 1;
    const type = inspectionStatusType(item);
    if (type === "success") summary.success += 1;
    else if (type === "danger") summary.danger += 1;
    else if (type === "warning") summary.warning += 1;
    else summary.other += 1;
    return summary;
  }, { total: 0, success: 0, danger: 0, warning: 0, other: 0 });
}

// 상단 요약 카드 필터와 실제 규칙 분류 매칭. '부적합' 카드는 danger+other 를 함께 포함(카드 표시 숫자와 동일 기준).
function inspectionItemMatchesFilter(item, filter) {
  if (!filter || filter === "total" || filter === "detail-total") return true;
  const type = inspectionStatusType(item);
  if (filter === "danger") return type === "danger" || type === "other";
  return type === filter;
}

function filterInspectionItems(items) {
  return items.filter((item) => inspectionItemMatchesFilter(item, state.inspectionFilter));
}

function inspectionStatusCell(rule, statusValue) {
  const manualOverride = manualOverrideOf(rule);
  const label = statusValue || rule.status_label || rule.status || "-";
  const badgeHtml = badge(label, { manualOverride });
  if (manualOverride) {
    return `
      <button
        type="button"
        class="status-badge-button manual-pass-note-button"
        data-manual-note-result="${escapeHtml(rule.id || "")}"
        data-manual-note-sub-key="${escapeHtml(rule.sub_check_key || "")}"
        title="${escapeHtml(manualOverride.memo || "수동 적합 사유")}"
      >${badgeHtml}</button>
    `;
  }
  if (rule.id && !isPassStatusValue(label)) {
    return `
      <button
        type="button"
        class="status-badge-button manual-pass-action-button"
        data-manual-pass-result="${escapeHtml(rule.id)}"
        data-manual-pass-sub-key="${escapeHtml(rule.sub_check_key || "")}"
        title="사유를 입력하고 수동으로 정상 처리"
      >${badgeHtml}</button>
    `;
  }
  return badgeHtml;
}

// 5가지 요약 카드를 클릭 가능한 버튼으로 렌더링한다. 클릭 시 아래 표가 해당 분류로 필터링된다.
function renderInspectionSummary(items, ruleItems = items) {
  const detailItems = Array.isArray(items) ? items : [];
  const ruleSummaryItems = Array.isArray(ruleItems) && ruleItems.length ? ruleItems : detailItems;
  const detailSummary = inspectionSummary(detailItems);
  const ruleSummary = inspectionSummary(ruleSummaryItems);
  const reviewNeeded = detailSummary.danger + detailSummary.other;
  const activeFilter = state.inspectionFilter;
  const cards = [
    { filter: "total", cls: "", label: "전체 규칙", count: ruleSummary.total, title: "저장된 부모 규칙 결과 수" },
    { filter: "detail-total", cls: "", label: "세부항목", count: detailSummary.total, title: "화면에 펼쳐진 세부 점검 항목 수" },
    { filter: "success", cls: "success", label: "정상 항목", count: detailSummary.success, title: "정상으로 판정된 세부항목 수" },
    { filter: "danger", cls: "danger", label: "부적합 항목", count: reviewNeeded, title: "부적합 또는 기타 상태의 세부항목 수" },
    { filter: "warning", cls: "warning", label: "확인 필요", count: detailSummary.warning, title: "확인이 필요한 세부항목 수" }
  ];
  return `
    <div class="inspection-summary" aria-label="규칙별 점검 요약(클릭하여 필터링)">
      ${cards.map((card) => `
        <button
          type="button"
          class="inspection-summary-card${card.cls ? ` ${card.cls}` : ""}${(activeFilter || "total") === card.filter ? " active" : ""}"
          data-inspection-filter="${card.filter}"
          title="${escapeHtml(card.title)}"
        >
          <span>${card.label}</span>
          <strong>${card.count}</strong>
        </button>
      `).join("")}
    </div>
  `;
}

// 규칙 결과 목록을 7열 테이블 행 HTML로 렌더링한다.
// 하위 검사가 여러 개면 행으로 분리하고, 번호/점검항목/파일명은 rowspan으로 묶는다.
// 하위 검사의 실제값이 기대값과 어긋나는(불일치) 행은 강조 표시한다.
function renderInspectionRows(items) {
  return items.map((rule) => {
    const subChecks = ruleSubChecks(rule);
    return subChecks.length ? renderInspectionSubCheckRows(rule, subChecks) : renderInspectionSingleRow(rule);
  }).join("");
}

function renderInspectionSingleRow(rule) {
  return `
    <tr>
      <td>${escapeHtml(rule.display_number || rule.sequence || "-")}</td>
      <td>${escapeHtml(rule.rule_name || "-")}</td>
      <td>${inspectionStatusCell(rule, rule.status_label || rule.status || "-")}</td>
      <td>${escapeHtml(rule.file_name || "-")}</td>
      <td>${escapeMultiline(rule.expected || "-")}</td>
      <td>${escapeMultiline(rule.actual || "-")}</td>
      <td>${formatIssueMessage(rule.message || "-")}</td>
    </tr>
  `;
}

function renderInspectionSubCheckRows(rule, subChecks) {
  const rowCount = subChecks.length;
  // 모든 하위 검사에 pass/fail 값이 있으면 행별로 배지를 나눠 보여주고,
  // 아니면(일부 항목만 판정 가능) 규칙 전체 배지를 rowspan 으로 공유한다.
  const perRowStatus = subChecks.every((sub) => typeof sub.passed === "boolean");
  return subChecks.map((sub, index) => {
    const mismatch = sub.passed === false;
    const subRule = {
      ...rule,
      sub_check_key: sub.sub_check_key || `sub-${index + 1}`,
      manual_override: sub.manual_override || rule.manual_override || null
    };
    const statusCell = perRowStatus
      ? `<td>${inspectionStatusCell(subRule, sub.passed ? "정상" : "부적합")}</td>`
      : (index === 0 ? `<td rowspan="${rowCount}">${inspectionStatusCell(subRule, rule.status_label || rule.status || "-")}</td>` : "");
    return `
      <tr${mismatch ? ' class="subcheck-row-mismatch"' : ""}>
        ${index === 0 ? `<td rowspan="${rowCount}">${escapeHtml(rule.display_number || rule.sequence || "-")}</td>` : ""}
        ${index === 0 ? `<td rowspan="${rowCount}">${escapeHtml(rule.rule_name || "-")}</td>` : ""}
        ${statusCell}
        ${index === 0 ? `<td rowspan="${rowCount}">${escapeHtml(rule.file_name || "-")}</td>` : ""}
        <td>${escapeMultiline(sub.expected || "-")}</td>
        <td class="${mismatch ? "cell-mismatch" : ""}">${escapeMultiline(sub.actual || "-")}</td>
        <td>${formatIssueMessage(sub.message || (mismatch ? "실제값이 기대값과 다릅니다." : "-"))}</td>
      </tr>
    `;
  }).join("");
}

function renderInspectionTableBlock(items) {
  const rows = renderInspectionRows(items);
  return `
    <table class="data-table" aria-label="규칙별 점검 결과">
      <thead>
        <tr>
          <th>번호</th>
          <th>점검항목</th>
          <th>결과</th>
          <th>파일명</th>
          <th>기대값</th>
          <th>실제값</th>
          <th>메시지</th>
        </tr>
      </thead>
      <tbody>${rows || `<tr><td class="empty-cell" colspan="7">선택한 분류에 해당하는 규칙이 없습니다.</td></tr>`}</tbody>
    </table>
  `;
}

function renderInspectionModalHelp() {
  return `
    <details class="help-panel modal-help">
      <summary>
        <span>
          <i class="fa-solid fa-circle-question" aria-hidden="true"></i>
          규칙별 점검 결과 도움말
        </span>
        <i class="fa-solid fa-chevron-down help-chevron" aria-hidden="true"></i>
      </summary>
      <div class="help-grid">
        <article class="help-item">
          <span class="help-icon"><i class="fa-solid fa-folder" aria-hidden="true"></i></span>
          <div>
            <strong>전체 산출물 다운로드</strong>
            <p>해당 프로젝트의 ECM에 업로드된 파일 전체를 다운로드합니다.</p>
          </div>
        </article>
        <article class="help-item">
          <span class="help-icon"><i class="fa-solid fa-table-list" aria-hidden="true"></i></span>
          <div>
            <strong>규칙별 점검 결과</strong>
            <p>결과 카테고리를 클릭해 필터링하고, 부적합 결과는 결과 배지를 클릭해 메모와 함께 수동 정상 처리할 수 있습니다.</p>
          </div>
        </article>
      </div>
    </details>
  `;
}

function renderInspectionResultContent(items, leadText = "", ruleItems = items) {
  return `
    <div class="inspection-result-shell">
      ${renderInspectionModalHelp()}
      ${leadText ? `<p class="modal-lead">${escapeHtml(leadText)}</p>` : ""}
      <div id="inspectionSummaryBlock">${renderInspectionSummary(items, ruleItems)}</div>
      <div class="table-wrap modal-table inspection-result-table" id="inspectionTableBlock">
        ${renderInspectionTableBlock(filterInspectionItems(items))}
      </div>
    </div>
  `;
}

// 규칙 결과 모달을 채우는 공용 진입점. 필터 상태를 초기화하고, 요약 카드 클릭 바인딩과
// 컬럼 너비 수동 조절(리사이즈)을 새로 삽입된 테이블에도 적용한다.
function mountInspectionResult(items, leadText = "", options = {}) {
  state.inspectionItems = Array.isArray(items) ? items : [];
  state.inspectionRuleItems = Array.isArray(options.ruleItems) && options.ruleItems.length
    ? options.ruleItems
    : state.inspectionItems;
  state.inspectionFilter = null;
  qs("modalBody").innerHTML = renderInspectionResultContent(
    state.inspectionItems,
    leadText,
    state.inspectionRuleItems
  );
  bindInspectionSummaryFilters();
  bindInspectionStatusActions();
  initResizableTables();
  fitVisibleResizableTables();
}

function bindInspectionSummaryFilters() {
  const summaryBlock = qs("inspectionSummaryBlock");
  if (!summaryBlock) return;
  summaryBlock.querySelectorAll("[data-inspection-filter]").forEach((card) => {
    card.addEventListener("click", () => {
      const raw = card.dataset.inspectionFilter;
      state.inspectionFilter = raw === "total" ? null : raw;
      refreshInspectionTable();
    });
  });
}

function refreshInspectionTable() {
  const summaryBlock = qs("inspectionSummaryBlock");
  const tableBlock = qs("inspectionTableBlock");
  if (summaryBlock) summaryBlock.innerHTML = renderInspectionSummary(state.inspectionItems, state.inspectionRuleItems);
  if (tableBlock) tableBlock.innerHTML = renderInspectionTableBlock(filterInspectionItems(state.inspectionItems));
  bindInspectionSummaryFilters();
  bindInspectionStatusActions();
  initResizableTables();
}

function bindInspectionStatusActions() {
  document.querySelectorAll("[data-manual-pass-result]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = findInspectionItemByResultId(
        button.dataset.manualPassResult,
        button.dataset.manualPassSubKey || ""
      );
      if (item) openManualPassPopup(item);
    });
  });
  document.querySelectorAll("[data-manual-note-result]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = findInspectionItemByResultId(
        button.dataset.manualNoteResult,
        button.dataset.manualNoteSubKey || ""
      );
      if (item) openManualPassNotePopup(item);
    });
  });
}

function findInspectionItemByResultId(resultId, subCheckKey = "") {
  const id = String(resultId || "");
  const key = String(subCheckKey || "");
  const sameResult = (item) => String(item.id || "") === id;
  const sameSubCheck = (item) => String(item.sub_check_key || "") === key;
  if (key) {
    return (
      state.inspectionItems.find((item) => sameResult(item) && sameSubCheck(item))
      || state.inspectionRuleItems.find((item) => sameResult(item) && sameSubCheck(item))
      || null
    );
  }
  return (
    state.inspectionItems.find((item) => sameResult(item) && manualOverrideOf(item))
    || state.inspectionRuleItems.find((item) => sameResult(item) && manualOverrideOf(item))
    || state.inspectionItems.find((item) => sameResult(item))
    || state.inspectionRuleItems.find((item) => sameResult(item))
    || null
  );
}

function findErrorItem(source, number) {
  if (source === "progress") {
    return state.activeProjects.find((item) => item.id === number || item.number === number) || null;
  }

  return state.resultProjects.find((item) => item.id === number);
}

async function openJobProjectRulesModal(jobProjectId, project = null) {
  const titleNumber = project?.number || jobProjectId;

  openModal({
    eyebrow: "점검 결과",
    title: `${titleNumber} 규칙별 점검 결과`,
    body: `<p class="modal-lead">점검 결과를 불러오는 중입니다.</p>`
  });

  try {
    const payload = await requestJson(`/api/job-projects/${jobProjectId}/results/`);
    const payloadProject = payload.project ? normalizeApiJobProject(payload.project) : {};
    const projectNumber = payloadProject.number || project?.number || titleNumber;
    const rawItems = Array.isArray(payload.items) ? payload.items : [];
    const displayItems = Array.isArray(payload.display_items) ? payload.display_items : rawItems;
    qs("modalTitle").textContent = `${projectNumber} 규칙별 점검 결과`;
    setModalDownload(`${projectNumber}_규칙별_점검_결과.html`);
    setModalFullFolderDownload({
      id: payloadProject.id || jobProjectId,
      number: projectNumber,
      certDate: payloadProject.certDate || project?.certDate || ""
    });
    setModalChangeNote(
      { id: payloadProject.id || jobProjectId, number: projectNumber },
      payloadProject.changeNote
    );

    if (displayItems.length) {
      mountInspectionResult(displayItems, `작업 프로젝트 ${projectNumber}의 규칙 결과입니다.`, { ruleItems: rawItems });
    } else {
      qs("modalBody").innerHTML = `
        <div class="modal-message warning">
          <strong>생성된 규칙 결과가 없습니다.</strong>
          <p>작업 자체가 실패했거나 아직 규칙 검사가 실행되지 않은 프로젝트입니다.</p>
        </div>
      `;
    }
  } catch (error) {
    qs("modalBody").innerHTML = `
      <div class="modal-message warning">
        <strong>${escapeHtml(error.message)}</strong>
        <p>규칙 결과를 다시 조회해 주세요.</p>
      </div>
    `;
  }
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
    const payloadProject = payload.project ? normalizeApiJobProject(payload.project) : {};
    const projectNumber = payloadProject.number || project.number;
    const rawItems = Array.isArray(payload.items) ? payload.items : [];
    const displayItems = Array.isArray(payload.display_items) ? payload.display_items : rawItems;
    setModalDownload(`${projectNumber}_규칙별_점검_결과.html`);
    setModalFullFolderDownload({
      ...project,
      number: projectNumber,
      certDate: payloadProject.certDate || project.certDate || ""
    });
    setModalChangeNote(
      { id: payloadProject.id || jobProjectId, number: projectNumber },
      payloadProject.changeNote
    );

    if (displayItems.length) {
      mountInspectionResult(displayItems, `작업 프로젝트 ${projectNumber}의 규칙 결과입니다.`, { ruleItems: rawItems });
    } else {
      qs("modalBody").innerHTML = `
        <div class="modal-message warning">
          <strong>생성된 규칙 결과가 없습니다.</strong>
          <p>작업 자체가 실패했거나 아직 규칙 검사가 실행되지 않은 프로젝트입니다.</p>
        </div>
      `;
    }
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

function bindProgressRuleResultButtons() {
  document.querySelectorAll("[data-progress-rule-result]").forEach((button) => {
    button.addEventListener("click", () => {
      const project = state.activeProjects.find((item) => item.id === button.dataset.progressRuleResult);
      openJobProjectRulesModal(button.dataset.progressRuleResult, project);
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

let progressPollingTimer = null;

function startProgressPolling() {
  if (progressPollingTimer) return;
  progressPollingTimer = setInterval(async () => {
    if (!qs("tab-progress").classList.contains("active")) return;
    await refreshActiveJob();
  }, 5000);
}

function stopProgressPolling() {
  if (progressPollingTimer) {
    clearInterval(progressPollingTimer);
    progressPollingTimer = null;
  }
}

let resultsPollingTimer = null;

function startResultsPolling() {
  if (resultsPollingTimer) return;
  resultsPollingTimer = setInterval(async () => {
    if (!qs("tab-results").classList.contains("active")) return;
    // 선택된 작업/필터를 유지한 채 조용히(silent) 갱신한다.
    await loadResultJobs(state.resultJobId, { silent: true });
  }, 5000);
}

function stopResultsPolling() {
  if (resultsPollingTimer) {
    clearInterval(resultsPollingTimer);
    resultsPollingTimer = null;
  }
}

let serverTimePollingTimer = null;

function koreaDateTimeInputValue(value) {
  if (!value) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23"
  }).formatToParts(new Date(value));
  const get = (type) => parts.find((item) => item.type === type)?.value || "";
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

function formatServerDateTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

function renderServerTime() {
  const data = state.serverTime;
  if (!data) return;
  const labels = {
    idle: "설정 가능",
    changing: "시간 변경 중",
    active: "임시 시간 사용 중",
    restoring: "정상 시간 복구 중",
    recovery_failed: "복구 확인 실패"
  };
  qs("serverTimeCurrent").textContent = formatServerDateTime(data.server_time);
  qs("serverTimeState").textContent = labels[data.status] || data.status;
  qs("serverTimeOwnerRow").hidden = !data.owner_name;
  qs("serverTimeOwner").textContent = data.owner_name || "-";
  qs("serverTimeRemainingRow").hidden = data.remaining_seconds == null;
  qs("serverTimeRemaining").textContent = data.remaining_seconds == null
    ? "-"
    : `${Math.floor(data.remaining_seconds / 60)}분 ${String(data.remaining_seconds % 60).padStart(2, "0")}초`;

  const idle = data.status === "idle";
  const ownerControl = data.status === "active" || data.status === "recovery_failed";
  const busy = !idle && !ownerControl;
  qs("serverTimeChange").hidden = !idle;
  qs("serverTimeReset").hidden = !ownerControl;
  qs("serverTimeTargetLabel").hidden = busy;
  qs("serverTimeName").disabled = busy;
  qs("serverTimePin").disabled = busy;
  qs("serverTimeTarget").disabled = busy;
  qs("serverTimeChange").disabled = !data.agent_online;
  qs("serverTimeReset").disabled = !data.agent_online;
  qs("serverTimeRestore").disabled = !ownerControl || !data.agent_online;
  qs("serverTimeRestore").title = ownerControl
    ? "현재 설정자의 이름과 비밀번호를 입력하면 즉시 원상복구합니다."
    : "변경 중인 ECM서버 시간이 있을 때 사용할 수 있습니다.";
  qs("serverTimeTarget").max = koreaDateTimeInputValue(data.normal_time_estimate);

  if (!data.agent_online) {
    qs("serverTimeNotice").textContent = "시간 변경 에이전트가 실행 중이 아니어서 현재 설정할 수 없습니다.";
  } else if (data.status === "recovery_failed") {
    qs("serverTimeNotice").textContent = data.error_message || "정상 시간 복구를 확인하지 못했습니다. 같은 이름과 PIN으로 다시 복구할 수 있습니다.";
  } else if (ownerControl) {
    qs("serverTimeNotice").textContent = "표시된 설정자와 동일한 이름 및 PIN으로 조기 복구하거나 과거 시간으로 재설정할 수 있습니다.";
  } else {
    qs("serverTimeNotice").textContent = "과거 날짜와 시간만 설정할 수 있으며 3분 뒤 자동으로 복구됩니다.";
  }
}

async function refreshServerTime({ silent = false } = {}) {
  try {
    state.serverTime = await requestJson(apiEndpoints.serverTime);
    renderServerTime();
    if (!silent) qs("serverTimeError").hidden = true;
  } catch (error) {
    if (!silent) {
      state.serverTime = null;
      qs("serverTimeCurrent").textContent = "확인 실패";
      qs("serverTimeState").textContent = "ECM서버 연결 확인 필요";
      qs("serverTimeOwnerRow").hidden = true;
      qs("serverTimeRemainingRow").hidden = true;
      qs("serverTimeChange").disabled = true;
      qs("serverTimeRestore").disabled = true;
      qs("serverTimeError").textContent = error.message;
      qs("serverTimeError").hidden = false;
    }
  }
}

async function openServerTimeModal() {
  qs("serverTimeModal").hidden = false;
  qs("serverTimeError").hidden = true;
  qs("serverTimeCurrent").textContent = "불러오는 중...";
  qs("serverTimeState").textContent = "확인 중";
  await refreshServerTime();
  if (serverTimePollingTimer) clearInterval(serverTimePollingTimer);
  serverTimePollingTimer = setInterval(() => refreshServerTime({ silent: true }), 1000);
}

function closeServerTimeModal() {
  qs("serverTimeModal").hidden = true;
  if (serverTimePollingTimer) {
    clearInterval(serverTimePollingTimer);
    serverTimePollingTimer = null;
  }
  qs("serverTimePin").value = "";
}

async function submitServerTimeAction(action) {
  const data = state.serverTime;
  if (!data) return;
  const button = action === "change" ? qs("serverTimeChange") : action === "reset" ? qs("serverTimeReset") : qs("serverTimeRestore");
  button.disabled = true;
  qs("serverTimeError").hidden = true;
  try {
    state.serverTime = await requestJson(apiEndpoints.serverTimeAction, {
      method: "POST",
      body: JSON.stringify({
        action,
        revision: data.revision,
        owner_name: qs("serverTimeName").value,
        pin: qs("serverTimePin").value,
        target_time: action === "restore" ? null : qs("serverTimeTarget").value
      })
    });
    qs("serverTimePin").value = "";
    renderServerTime();
  } catch (error) {
    qs("serverTimeError").textContent = error.message;
    qs("serverTimeError").hidden = false;
    await refreshServerTime({ silent: true });
  } finally {
    renderServerTime();
  }
}

async function refreshTabData(tab) {
  if (tab === "projects") {
    await loadProjects();
    await refreshActiveJob();
    return;
  }
  if (tab === "progress") {
    await refreshActiveJob();
    return;
  }
  if (tab === "results") {
    await loadResultJobs(state.resultJobId);
  }
}

function bindControls() {
  qs("openServerTime").addEventListener("click", openServerTimeModal);
  qs("closeServerTimeModal").addEventListener("click", closeServerTimeModal);
  qs("serverTimeChange").addEventListener("click", () => submitServerTimeAction("change"));
  qs("serverTimeReset").addEventListener("click", () => submitServerTimeAction("reset"));
  qs("serverTimeRestore").addEventListener("click", () => submitServerTimeAction("restore"));
  qs("serverTimeModal").addEventListener("click", (event) => {
    if (event.target === qs("serverTimeModal")) closeServerTimeModal();
  });
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const tab = button.dataset.tab;
      document.querySelectorAll(".tab-button").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      qs(`tab-${tab}`).classList.add("active");
      if (tab === "progress") {
        startProgressPolling();
        stopResultsPolling();
      } else if (tab === "results") {
        startResultsPolling();
        stopProgressPolling();
      } else {
        stopProgressPolling();
        stopResultsPolling();
      }
      await refreshTabData(tab);
      // 탭이 보이게 된 직후 해당 테이블 너비를 컨테이너에 맞춘다.
      fitVisibleResizableTables();
    });
  });

  let resizeFitTimer = null;
  window.addEventListener("resize", () => {
    if (resizeFitTimer) clearTimeout(resizeFitTimer);
    resizeFitTimer = setTimeout(fitVisibleResizableTables, 150);
  });

  ["filterProject", "filterCompany", "filterProduct", "filterPl", "filterStatus"].forEach((id) => {
    qs(id).addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      qs("searchProjects").click();
    });
  });
  qs("searchProjects").addEventListener("click", applyProjectFilters);

  qs("openPlAssignment").addEventListener("click", openPlAssignmentModal);
  qs("closePlAssignmentModal").addEventListener("click", closePlAssignmentModal);
  qs("cancelPlAssignment").addEventListener("click", closePlAssignmentModal);
  qs("confirmPlAssignment").addEventListener("click", confirmPlAssignmentChanges);
  qs("plAssignMoveRight").addEventListener("click", () => movePlAssignmentSelection("left", "right"));
  qs("plAssignMoveLeft").addEventListener("click", () => movePlAssignmentSelection("right", "left"));
  qs("plAssignmentModal").addEventListener("click", (event) => {
    if (event.target === qs("plAssignmentModal")) closePlAssignmentModal();
  });

  document.querySelectorAll("[data-center-tab]").forEach((button) => {
    button.addEventListener("click", async () => {
      await switchCenter(button.dataset.centerTab);
    });
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
    const jobNumbers = [...state.selected].filter((number) => {
      const item = mockProjects.find((project) => project.number === number);
      return isProjectSelectable(item);
    });
    const count = jobNumbers.length;
    if (count === 0) return;

    qs("requestJob").disabled = true;
    state.selectionMessage = "작업 요청을 등록하는 중입니다.";
    renderSelection();

    try {
      const payload = await requestJson(apiEndpoints.jobs, {
        method: "POST",
        body: JSON.stringify({ center: state.center, project_numbers: jobNumbers })
      });
      state.selectionMessage = payload.message || `${count}개 프로젝트가 등록되었습니다.`;
      state.resultJobId = payload.job_id || state.resultJobId;
      state.resultJobCenter = "all";
      state.resultPagination.offset = 0;
      state.selected.clear();
      await refreshActiveJob();
      await loadProjects();
      await loadResultJobs(payload.job_id, { resetPage: true });
      openRequestCompleteModal(payload, count);
    } catch (error) {
      state.selectionMessage = error.message;
      renderSelection();
    }
  });

  qs("downloadJobResults").addEventListener("click", downloadJobResults);
  qs("bulkDownload").addEventListener("click", bulkDownloadSelected);

  document.querySelectorAll("[data-job-center-tab]").forEach((button) => {
    button.addEventListener("click", async () => {
      const nextCenter = button.dataset.jobCenterTab || "all";
      if (state.resultJobCenter === nextCenter) return;
      state.resultJobCenter = nextCenter;
      state.resultJobId = null;
      state.resultProjects = [];
      renderJobCenterTabs();
      await loadResultJobs(null, { resetPage: true });
    });
  });

  qs("jobListPager").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-job-page]");
    if (!button || button.disabled) return;

    const limit = state.resultPagination.limit || jobListPageSize;
    const offset = state.resultPagination.offset || 0;
    const direction = button.dataset.jobPage;
    state.resultPagination.offset = direction === "prev"
      ? Math.max(0, offset - limit)
      : offset + limit;
    state.resultJobId = null;
    state.resultProjects = [];
    await loadResultJobs();
  });

  document.querySelectorAll("[data-result-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-result-filter]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.resultFilter = button.dataset.resultFilter;
      renderResults();
    });
  });

  const forceStopButton = qs("forceStopButton");
  if (forceStopButton) {
    forceStopButton.addEventListener("click", openForceStopModal);
  }

  qs("closeModal").addEventListener("click", closeModal);
  qs("modalDownload").addEventListener("click", downloadCurrentModalHtml);
  qs("modalChangeNote").addEventListener("click", openCurrentProjectChangeNote);
  qs("modalFullFolderDownload").addEventListener("click", downloadCurrentProjectFullFolder);
  qs("closeChangeNoteModal").addEventListener("click", closeChangeNotePopup);
  qs("closeManualOverrideModal").addEventListener("click", closeManualPassPopup);
  qs("cancelManualOverride").addEventListener("click", closeManualPassPopup);
  qs("confirmManualOverride").addEventListener("click", confirmManualPassOverride);
  qs("changeNoteModal").addEventListener("click", (event) => {
    if (event.target === qs("changeNoteModal")) closeChangeNotePopup();
  });
  qs("manualOverrideModal").addEventListener("click", (event) => {
    if (event.target === qs("manualOverrideModal")) closeManualPassPopup();
  });
  qs("detailModal").addEventListener("click", (event) => {
    if (event.target === qs("detailModal")) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!qs("serverTimeModal").hidden) {
      closeServerTimeModal();
      return;
    }
    if (!qs("plAssignmentModal").hidden) {
      closePlAssignmentModal();
      return;
    }
    if (!qs("manualOverrideModal").hidden) {
      closeManualPassPopup();
      return;
    }
    if (!qs("changeNoteModal").hidden) {
      closeChangeNotePopup();
      return;
    }
    closeModal();
  });
}

async function switchCenter(center) {
  if (!center || center === state.center) return;
  const remoteUrl = centerRoutes[center];
  if (remoteUrl) {
    window.location.assign(buildCenterRouteUrl(remoteUrl, center));
    return;
  }
  if (!allowedCenters.has(center)) return;
  state.center = center;
  state.selectionMessage = "";
  state.selected.clear();
  resetProjectFilters();
  syncCenterTabs();
  await loadProjects();
}

function buildCenterRouteUrl(baseUrl, center) {
  const url = new URL(baseUrl, window.location.href);
  url.searchParams.set("center", center);
  return url.toString();
}

function syncCenterTabs() {
  document.querySelectorAll("[data-center-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.centerTab === state.center);
  });
  qs("openServerTime").hidden = state.center !== "sangam" && state.center !== "yeongnam";
}

async function init() {
  updateClock();
  bindControls();
  initResizableTables();
  syncCenterTabs();
  resetProjectFilters();
  populateFilters();
  renderProjects();
  await loadProjects();
  // 행 렌더링/스크롤바 상태 확정 후 표 너비를 컨테이너에 맞춘다.
  fitVisibleResizableTables();
  await refreshActiveJob();
  await loadResultJobs();
  setInterval(updateClock, 1000);
}

document.addEventListener("DOMContentLoaded", init);
