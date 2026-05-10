const mockProjects = [
  {
    number: "TTA-26-00009",
    certDate: "2026.05.08",
    company: "우리데이터 주식회사",
    product: "우리데이터클리닉 V1.0",
    pl: "박지훈",
    review: "완료",
    contract: "있음",
    reportPdf: "대상",
    copyright: "대상"
  },
  {
    number: "TTA-26-00010",
    certDate: "2026.05.09",
    company: "에이치소프트",
    product: "SecureFlow 2.1",
    pl: "김준호",
    review: "진행",
    contract: "있음",
    reportPdf: "대상",
    copyright: "대상"
  },
  {
    number: "TTA-26-00011",
    certDate: "2026.05.10",
    company: "다온테크",
    product: "DaonOps Cloud",
    pl: "이수민",
    review: "대기",
    contract: "미확인",
    reportPdf: "대상",
    copyright: "미대상"
  },
  {
    number: "TTA-26-00012",
    certDate: "2026.05.10",
    company: "넥스트랩",
    product: "NextLab QA Suite",
    pl: "박지훈",
    review: "완료",
    contract: "있음",
    reportPdf: "대상",
    copyright: "대상"
  },
  {
    number: "TTA-26-00013",
    certDate: "2026.05.11",
    company: "그린인사이트",
    product: "GreenWatch v3",
    pl: "최유진",
    review: "보류",
    contract: "미확인",
    reportPdf: "대상",
    copyright: "대상"
  }
];

const mockActiveJob = {
  id: "JOB-20260510-004",
  status: "running",
  total: 5,
  completed: 2,
  failed: 1,
  currentProject: "TTA-26-00012",
  currentStep: "TTA-26-00012 전송현황 완료 대기 중",
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
      product: "우리데이터클리닉 V1.0",
      status: "completed",
      step: "다운로드 완료",
      retry: 0,
      zip: "00009 TTA-26-00009(완료) 우리데이터 주식회사(우리데이터클리닉 V1.0).zip",
      error: ""
    },
    {
      number: "TTA-26-00010",
      company: "에이치소프트",
      product: "SecureFlow 2.1",
      status: "completed",
      step: "중복 알림 후 폴더 변경 재시도 완료",
      retry: 1,
      zip: "00010 TTA-26-00010(완료) 에이치소프트(SecureFlow 2.1).zip",
      error: ""
    },
    {
      number: "TTA-26-00011",
      company: "다온테크",
      product: "DaonOps Cloud",
      status: "failed",
      step: "zip 파일 확인",
      retry: 2,
      zip: "",
      error: "전송현황 종료 후 zip 파일을 찾을 수 없음"
    },
    {
      number: "TTA-26-00012",
      company: "넥스트랩",
      product: "NextLab QA Suite",
      status: "running",
      step: "전송현황 완료 대기 중",
      retry: 0,
      zip: "",
      error: ""
    },
    {
      number: "TTA-26-00013",
      company: "그린인사이트",
      product: "GreenWatch v3",
      status: "pending",
      step: "대기",
      retry: 0,
      zip: "",
      error: ""
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
        error: ""
      },
      {
        number: "TTA-26-00005",
        company: "메타브릿지",
        product: "MetaBridge Hub",
        status: "failed",
        zip: "",
        failStep: "폴더 찾아보기",
        error: "다운로드 폴더 트리에서 대상 폴더 선택 실패"
      },
      {
        number: "TTA-26-00006",
        company: "오션소프트",
        product: "OceanDesk",
        status: "success",
        zip: "00006 TTA-26-00006(완료) 오션소프트(OceanDesk).zip",
        failStep: "",
        error: ""
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
        error: ""
      },
      {
        number: "TTA-26-00002",
        company: "비전아이",
        product: "VisionEye",
        status: "success",
        zip: "00002 TTA-26-00002(완료) 비전아이(VisionEye).zip",
        failStep: "",
        error: ""
      },
      {
        number: "TTA-26-00003",
        company: "제이테크",
        product: "J-Report",
        status: "success",
        zip: "00003 TTA-26-00003(완료) 제이테크(J-Report).zip",
        failStep: "",
        error: ""
      },
      {
        number: "TTA-26-00007",
        company: "알파랩",
        product: "AlphaTest",
        status: "success",
        zip: "00007 TTA-26-00007(완료) 알파랩(AlphaTest).zip",
        failStep: "",
        error: ""
      }
    ]
  }
];

const state = {
  selected: new Set(["TTA-26-00009", "TTA-26-00012"]),
  focusedProject: mockProjects[0],
  resultJobId: mockJobs[0].id,
  resultFilter: "all",
  heartbeatWarning: false
};

const statusLabel = {
  pending: ["대기", "badge-muted"],
  running: ["진행 중", "badge-run"],
  downloaded: ["다운로드 완료", "badge-run"],
  inspecting: ["검사 중", "badge-run"],
  completed: ["완료", "badge-success"],
  failed: ["실패", "badge-danger"],
  skipped: ["건너뜀", "badge-warn"],
  success: ["성공", "badge-success"]
};

function qs(id) {
  return document.getElementById(id);
}

function badge(status) {
  const config = statusLabel[status] || [status, "badge-muted"];
  return `<span class="badge ${config[1]}">${config[0]}</span>`;
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
  qs("projectRows").innerHTML = rows.map((item) => {
    const checked = state.selected.has(item.number) ? "checked" : "";
    const selected = state.focusedProject?.number === item.number ? "selected" : "";
    return `
      <tr class="${selected}" data-project-row="${item.number}">
        <td class="check-col">
          <input type="checkbox" data-project-check="${item.number}" ${checked} aria-label="${item.number} 선택">
        </td>
        <td><strong>${item.number}</strong></td>
        <td>${item.certDate}</td>
        <td>${item.company}</td>
        <td>${item.product}</td>
        <td>${item.pl}</td>
        <td>${item.review}</td>
      </tr>
    `;
  }).join("");

  qs("selectVisible").checked = rows.length > 0 && rows.every((item) => state.selected.has(item.number));
  bindProjectRows();
  renderSelection();
  renderDetail();
}

function bindProjectRows() {
  document.querySelectorAll("[data-project-check]").forEach((checkbox) => {
    checkbox.addEventListener("click", (event) => {
      event.stopPropagation();
      const number = checkbox.dataset.projectCheck;
      if (checkbox.checked) {
        state.selected.add(number);
      } else {
        state.selected.delete(number);
      }
      renderProjects();
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
    : `<p class="muted">선택한 프로젝트가 없습니다.</p>`;

  qs("lockMessage").textContent = "현재 다른 작업이 진행 중입니다. 완료 후 다시 요청해 주세요.";
  qs("requestJob").disabled = true;
}

function renderDetail() {
  const item = state.focusedProject;
  if (!item) {
    qs("projectDetail").innerHTML = `
      <h3>프로젝트 상세</h3>
      <p class="muted">목록에서 행을 선택하면 ecm 컬럼 요약을 표시합니다.</p>
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
      <dt>점검결과</dt><dd>${item.review}</dd>
      <dt>계약서</dt><dd>${item.contract}</dd>
      <dt>시험성적서(PDF)</dt><dd>${item.reportPdf}</dd>
      <dt>SW저작권확인서</dt><dd>${item.copyright}</dd>
    </dl>
  `;
}

function renderProgress() {
  qs("jobId").textContent = mockActiveJob.id;
  qs("jobProgress").textContent = `${mockActiveJob.completed} / ${mockActiveJob.total}`;
  qs("currentProject").textContent = mockActiveJob.currentProject;
  qs("failedCount").textContent = `${mockActiveJob.failed}건`;
  qs("currentStep").textContent = mockActiveJob.currentStep;
  qs("progressBar").style.width = `${Math.round((mockActiveJob.completed / mockActiveJob.total) * 100)}%`;

  const worker = {
    ...mockActiveJob.worker,
    stale: state.heartbeatWarning,
    heartbeat: state.heartbeatWarning ? "2026-05-10 14:20:03" : mockActiveJob.worker.heartbeat
  };

  qs("workerBox").className = `worker-box ${worker.stale ? "warning" : ""}`;
  qs("workerBox").innerHTML = `
    <div>
      <strong>${worker.stale ? "작업 실행기의 heartbeat가 지연되고 있습니다." : "작업 실행기가 정상 동작 중입니다."}</strong>
      <div>PID ${worker.pid} · 마지막 heartbeat ${worker.heartbeat}</div>
    </div>
    <span class="badge ${worker.stale ? "badge-warn" : "badge-success"}">${worker.stale ? "지연" : "정상"}</span>
  `;

  qs("workerState").innerHTML = `
    <span class="dot ${worker.stale ? "dot-warn" : "dot-ok"}"></span>
    <div><span class="label">Worker</span><strong>${worker.stale ? "지연" : "실행 중"}</strong></div>
  `;

  qs("progressRows").innerHTML = mockActiveJob.projects.map((item, index) => `
    <tr>
      <td>${index + 1}</td>
      <td><strong>${item.number}</strong></td>
      <td>${item.company}</td>
      <td>${item.product}</td>
      <td>${badge(item.status)}</td>
      <td>${item.step}</td>
      <td>${item.retry}</td>
      <td>${item.zip || "-"}</td>
      <td>${item.error || "-"}</td>
    </tr>
  `).join("");
}

function renderJobs() {
  qs("jobList").innerHTML = mockJobs.map((job) => `
    <button class="job-card ${state.resultJobId === job.id ? "active" : ""}" type="button" data-job-id="${job.id}">
      <div class="job-title">
        <span>${job.id}</span>
        ${badge(job.status)}
      </div>
      <div class="job-meta">
        <span>요청 ${job.requestedAt}</span>
        <span>완료 ${job.completedAt}</span>
        <span>전체 ${job.total}</span>
        <span>성공 ${job.success} / 실패 ${job.failed}</span>
      </div>
    </button>
  `).join("");

  document.querySelectorAll("[data-job-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.resultJobId = button.dataset.jobId;
      renderJobs();
      renderResults();
    });
  });
}

function renderResults() {
  const job = mockJobs.find((item) => item.id === state.resultJobId);
  qs("resultCaption").textContent = `${job.id} · 성공 ${job.success}건 · 실패 ${job.failed}건`;

  const rows = job.projects.filter((item) => (
    state.resultFilter === "all" ||
    (state.resultFilter === "success" && item.status === "success") ||
    (state.resultFilter === "failed" && item.status === "failed")
  ));

  qs("resultRows").innerHTML = rows.map((item) => `
    <tr>
      <td><strong>${item.number}</strong></td>
      <td>${item.company}</td>
      <td>${item.product}</td>
      <td>${badge(item.status)}</td>
      <td>${item.zip || "-"}</td>
      <td>${item.failStep || "-"}</td>
      <td>${item.error || "-"}</td>
    </tr>
  `).join("");
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

  qs("clearFilters").addEventListener("click", () => {
    qs("filterProject").value = "";
    qs("filterCompany").value = "";
    qs("filterProduct").value = "";
    qs("filterPl").value = "전체";
    qs("filterStatus").value = "전체";
    renderProjects();
  });

  qs("selectVisible").addEventListener("change", () => {
    filteredProjects().forEach((item) => {
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
    renderProjects();
  });

  qs("toggleHeartbeat").addEventListener("click", () => {
    state.heartbeatWarning = !state.heartbeatWarning;
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
}

function init() {
  updateClock();
  populateFilters();
  bindControls();
  renderProjects();
  renderProgress();
  renderJobs();
  renderResults();
  setInterval(updateClock, 1000);
}

document.addEventListener("DOMContentLoaded", init);
