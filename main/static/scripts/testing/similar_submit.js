document.addEventListener('DOMContentLoaded', function () {  
  const form = document.getElementById('queryForm'); // 제출 폼
  const fileInput = document.getElementById('fileInput');       // 파일 input
  const manualInput = document.getElementById('manualInput');   // 수동입력 textarea
  const contentManual = document.getElementById('content-manual'); // 수동입력 탭 컨테이너
  const loading = document.getElementById('loadingContainer');
  const summaryContent = document.getElementById('summaryContent');
  const resultsContent = document.getElementById('resultsContent');
  const resultsHeader = document.getElementById('resultsHeader');
  const inputSummary = document.getElementById('inputSummary');

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        // Does this cookie string begin with the name we want?
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
  
  function showLoading() {
    loading.classList.remove('hidden');
    resultsHeader.classList.add('hidden');
    inputSummary.classList.add('hidden');
    resultsContent.classList.add('hidden');
  }
  function hideLoading() {
    loading.classList.add('hidden');
    resultsHeader.classList.remove('hidden');
    inputSummary.classList.remove('hidden');
    resultsContent.classList.remove('hidden');
  }

  form.addEventListener('submit', function(e) {
    e.preventDefault()
    showLoading();

    try {
      setTimeout(function() {
        const summaryhtml = `홈페이지 및 문서 정보를 기반으로 자연어 대화로 안내하고 할루시네이션 없는 정확한 정보를 제공하는 AI 챗봇 시스템`;
        const resulthtml = `
<div class="results-content" id="resultsContent">
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜사미텍<br>Samitech.Inc</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">SAMI GPT v1.0<br>(SAMI GPT v1.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 54.33%</div>
            </div>
            <div class="product-description">
              Gemma 3와 연동하여 사용자가 업로드한 문서 파일 내용을 기반으로 질의응답을 제공하는 대화형 AI 프로그램
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2025.08.11</span>
              <p>시험번호</p><span class="product-tag">GS-C-25-0047</span>
              <p>WD</p><span class="product-tag"> GS-C-25-0034, 20WD
    GS-C-25-0047(1차), 4WD
      --&gt; 총 WD = 24</span>
              <p>시험기간</p><span class="product-tag">2025-06-19~2025-07-28</span>
              <p>시험원</p><span class="product-tag">전지은,김현규</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">주식회사 새움소프트 SaeumSoft</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">생성형 AI+KMS 챗봇 애니톡 2.0<br>(Generative AI+KMS chatbot Anytalk 2.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 54.64%</div>
            </div>
            <div class="product-description">
              기업 전용 생성형 챗봇 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2025.07.07</span>
              <p>시험번호</p><span class="product-tag">GS-A-25-0060</span>
              <p>WD</p><span class="product-tag">17</span>
              <p>시험기간</p><span class="product-tag">2025-05-21~2025-06-16</span>
              <p>시험원</p><span class="product-tag">구자경,한정우</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜그노티<br>Gnoti. Co., Ltd.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">GAIA v1.0<br>(GAIA v1.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 56.37%</div>
            </div>
            <div class="product-description">
              본 제품은 챗봇 대화용 데이터 관리를 통해 사용자별 질의응답 생성 기능을 제공하는 챗봇 프로그램으로 주요 기능은 다음과 같다.
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2025.06.09</span>
              <p>시험번호</p><span class="product-tag">GS-A-25-0042</span>
              <p>WD</p><span class="product-tag">19</span>
              <p>시험기간</p><span class="product-tag">2025-04-16~2025-05-15</span>
              <p>시험원</p><span class="product-tag">최재은, 김다은</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">주식회사 이로운앤컴퍼니<br>eRoun&amp;Company Co., Ltd. </td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">세이프엑스 v1.0<br>(SAIFE X v1.0 )</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 54.46%</div>
            </div>
            <div class="product-description">
              생성형 AI(GPT, Claude)를 통한 대화 기능을 지원하고, 대화 내 개인/민감 정보를 탐지하기 위한 프로그램
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2024.11.18</span>
              <p>시험번호</p><span class="product-tag">GS-A-24-0271</span>
              <p>WD</p><span class="product-tag">14</span>
              <p>시험기간</p><span class="product-tag">2024-10-21~2024-11-07</span>
              <p>시험원</p><span class="product-tag">이유겸, 이우진</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜솔트룩스<br>Saltlux Inc.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">학교폭력 정보제공형 인공지능 챗봇 v1.0<br>(School violence information-providing artificial intelligence(AI) chatbot v1.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 58.83%</div>
            </div>
            <div class="product-description">
              학교폭력 피해자와 대화를 통해 문제 해결 정보를 제공하기 위한 챗봇 프로그램
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2024.04.01</span>
              <p>시험번호</p><span class="product-tag">GS-A-23-0499</span>
              <p>WD</p><span class="product-tag">17</span>
              <p>시험기간</p><span class="product-tag">2023-12-13~2024-02-28</span>
              <p>시험원</p><span class="product-tag">박현권,이혜진,최주용(인),이하은,나유진(인)</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">와우커뮤니케이션㈜<br>WOW COMMUNICATION.INC</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">큐봇 v2.0<br>(Q-BOT v2.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 54.66%</div>
            </div>
            <div class="product-description">
              제품은 챗봇 대화용 데이터를 입력하여 주제별(POS 사용법 상담, 신용카드 서비스 상담) 챗봇을 생성하고, 챗봇 사용현황을 모니터링하는 프로그램
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2024.01.29</span>
              <p>시험번호</p><span class="product-tag">GS-A-24-0005</span>
              <p>WD</p><span class="product-tag">28</span>
              <p>시험기간</p><span class="product-tag">2023-11-27~2024-01-23</span>
              <p>시험원</p><span class="product-tag">윤범상, 임홍담</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜솔트룩스<br>Saltlux Inc.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">톡봇 스튜디오 v4.0<br>(Talkbot Studio v4.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 61.09%</div>
            </div>
            <div class="product-description">
              메신저 채널 서비스와 연동하여 질의 응답 및 시나리오 기반 대화 서비스를 개발 및 운영하는 챗봇 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2023.12.18</span>
              <p>시험번호</p><span class="product-tag">GS-A-23-020</span>
              <p>WD</p><span class="product-tag">17</span>
              <p>시험기간</p><span class="product-tag">2023-05-15~2023-12-12</span>
              <p>시험원</p><span class="product-tag">박현권,송원진,임홍담<br>박현권,이혜진,최주용</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">주식회사 프로텐<br>Proten Co., Ltd. </td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">프로챗 v1.0<br>(ProChat v1.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 60.82%</div>
            </div>
            <div class="product-description">
              본 제품은 텍스트로 입력된 사용자 질의에 대해 자동 응답을 제공하는 챗봇 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2023.04.03</span>
              <p>시험번호</p><span class="product-tag">GS-B-22-310</span>
              <p>WD</p><span class="product-tag">28</span>
              <p>시험기간</p><span class="product-tag">2023-02-09~2023-03-21</span>
              <p>시험원</p><span class="product-tag">박지훈, 정영재</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">아일리스프런티어㈜<br>AilysFrontier</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">다빈치봇 v3.1<br>(DAVinCI BOT v3.1)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 65.68%</div>
            </div>
            <div class="product-description">
              사용자 질의에 대해 자동 응답 또는 상담사 연결을 제공해주는 챗봇 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2023.02.16</span>
              <p>시험번호</p><span class="product-tag">GS-A-22-164</span>
              <p>WD</p><span class="product-tag">28</span>
              <p>시험기간</p><span class="product-tag">2022-12-28~2023-02-07</span>
              <p>시험원</p><span class="product-tag">노남규, 박솔화</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">한솔인티큐브㈜<br>Hansol Inticube Co., Ltd. </td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">인티큐브 아이작 v2.1<br>(Inticube ISAC v2.1)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 66.27%</div>
            </div>
            <div class="product-description">
              음성대화 및 문자로 입력된 사용자 질의의 대해 자동 응답을 제공하는 챗봇 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2022.10.24</span>
              <p>시험번호</p><span class="product-tag">GS-B-22-145</span>
              <p>WD</p><span class="product-tag">28</span>
              <p>시험기간</p><span class="product-tag">2022-08-22~2022-10-04</span>
              <p>시험원</p><span class="product-tag">홍승국, 이승주</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">주식회사 이즈소프트<br>EASE Soft Co., Ltd.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">파인딥 챗봇 v1.0<br>(FINDEEP ChatBot v1.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 60.95%</div>
            </div>
            <div class="product-description">
              사용자 질의에 대해 자동 응답을 제공하는 챗봇 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2022.08.08</span>
              <p>시험번호</p><span class="product-tag">GS-B-22-150</span>
              <p>WD</p><span class="product-tag">20</span>
              <p>시험기간</p><span class="product-tag">2022-06-27~2022-07-22</span>
              <p>시험원</p><span class="product-tag">박지훈, 은동현</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜스위트케이<br>SWEETK Co., Ltd.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">인공지능챗봇 레미 v1.0<br>(AI Chatbot REMI v1.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 56.30%</div>
            </div>
            <div class="product-description">
              본 제품은 텐서플로우와 연동하여 사용자 질의에 대한 챗봇 모델을 관리하고 자동 응답을 제공하는 챗봇 프로그램
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2022.04.07</span>
              <p>시험번호</p><span class="product-tag">GS-A-21-606</span>
              <p>WD</p><span class="product-tag">27</span>
              <p>시험기간</p><span class="product-tag">2021-09-14~2022-03-23</span>
              <p>시험원</p><span class="product-tag">장유원</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">주식회사 포티투마루<br>42Maru Inc.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">챗42 v1.0 <br>(Chat42 v1.00</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 60.95%</div>
            </div>
            <div class="product-description">
              사용자 질의에 대해 자동 응답을 제공하는 챗봇 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2022.04.04</span>
              <p>시험번호</p><span class="product-tag">GS-B-21-347</span>
              <p>WD</p><span class="product-tag">30</span>
              <p>시험기간</p><span class="product-tag">2022-02-08~2022-03-23</span>
              <p>시험원</p><span class="product-tag">변은영, 김선우</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜코난테크놀로지<br>Konan Technolgy Inc.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">코난 챗봇 3<br>(Konan Chatbot 3)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 58.20%</div>
            </div>
            <div class="product-description">
              사용자 질의에 대해 설정한 도메인과 시나리오에 의한 답변을 제공하는 챗봇 프로그램
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2022.02.24</span>
              <p>시험번호</p><span class="product-tag">GS-B-21-303</span>
              <p>WD</p><span class="product-tag">22</span>
              <p>시험기간</p><span class="product-tag">2021-11-22~2022-02-14</span>
              <p>시험원</p><span class="product-tag">홍승국, 배용훈</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜티맥스에이아이<br>TmaxAI Co., Ltd.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">하이퍼챗봇 v1.0.0<br>(Hyperchatbot v1.0.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 61.02%</div>
            </div>
            <div class="product-description">
              챗봇 엔진과 연동하여 사용자 질의에 대한 자동 응답을 간편하게 등록 및 관리할 수 있는 챗봇 응답 데이터 관리 시스템
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2021.12.13</span>
              <p>시험번호</p><span class="product-tag">GS-A-21-340</span>
              <p>WD</p><span class="product-tag">23</span>
              <p>시험기간</p><span class="product-tag">2021-11-03~2021-12-03</span>
              <p>시험원</p><span class="product-tag">김유진, 김민지</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜ 다이퀘스트<br>diquest Inc.<br>(구 : ㈜엔에이치엔다이퀘스트<br>NHN diquest Inc.)</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">인포채터3 <br>(INFOCHATTER3)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 60.95%</div>
            </div>
            <div class="product-description">
              사용자 질의에 대해 자동 응답을 제공하는 챗봇 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2021.11.29</span>
              <p>시험번호</p><span class="product-tag">GS-B-21-123</span>
              <p>WD</p><span class="product-tag">30</span>
              <p>시험기간</p><span class="product-tag">2021-10-05~2021-11-16</span>
              <p>시험원</p><span class="product-tag">변은영, 오정수</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜마인드웨어웍스(Mindwareworks Inc.<br>(구: ㈜마인드웨어웤스<br>Mindwareworks Inc.)</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">코그인사이트 3.0<br>(CogInsight 3.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 66.19%</div>
            </div>
            <div class="product-description">
              외부의 자연어 처리 서버와 연동하여 입력된 사용자 질의에 자동 응답을 제공하는 챗봇 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2021.09.16</span>
              <p>시험번호</p><span class="product-tag">GS-B-21-004</span>
              <p>WD</p><span class="product-tag">35</span>
              <p>시험기간</p><span class="product-tag">2021-07-16~2021-09-03</span>
              <p>시험원</p><span class="product-tag">최민경, 김혜리</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜이노그루<br>INNOGRU Inc.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">BAMS A.I.Talk 지능형 응답 챗봇 v1.0<br>(BAMS A.I.Talk Intelligent Response Chatbot v1.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 60.67%</div>
            </div>
            <div class="product-description">
              외부 챗봇 엔진과 연동하여 사용자 질의에 대한 자동 응답을 간편하게 등록 및 관리할 수 있는 챗봇 응답 데이터 관리 시스템
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2021.08.02</span>
              <p>시험번호</p><span class="product-tag">GS-A-21-152</span>
              <p>WD</p><span class="product-tag">12</span>
              <p>시험기간</p><span class="product-tag">2021-07-07~2021-07-22</span>
              <p>시험원</p><span class="product-tag">이강민</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜미소정보기술<br>MISO Info Tech Inc.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">미소봇 v1.0<br>(Misobot v1.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 62.63%</div>
            </div>
            <div class="product-description">
              텍스트로 입력된 사용자 질의에 대해 자동 응답을 제공하는 챗봇 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2021.03.15</span>
              <p>시험번호</p><span class="product-tag">GS-A-20-543</span>
              <p>WD</p><span class="product-tag">22</span>
              <p>시험기간</p><span class="product-tag">2021-01-29~2021-03-04</span>
              <p>시험원</p><span class="product-tag">정광락, 박민주</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜아이브릭스<br>I-BRICKS Inc.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">티아나 챗 v2.0<br>(TeAna Chat v2.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 66.02%</div>
            </div>
            <div class="product-description">
              텍스트로 입력된 사용자 질의에 자연어 처리 기반의 응답을제공하는 챗봇 서비스 프로그램
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2020.10.05</span>
              <p>시험번호</p><span class="product-tag">GS-A-20-204</span>
              <p>WD</p><span class="product-tag">22</span>
              <p>시험기간</p><span class="product-tag">2020-08-24~2020-09-22</span>
              <p>시험원</p><span class="product-tag">신우준, 이의성</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜와이즈넛<br>WISEnut, Inc</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">와이즈 아이챗 V3<br>(WISE i Chat V3)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 62.63%</div>
            </div>
            <div class="product-description">
              텍스트로 입력된 사용자 질의에 대해 자동 응답을 제공하는 챗봇 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2020.09.21</span>
              <p>시험번호</p><span class="product-tag">GS-A-20-365</span>
              <p>WD</p><span class="product-tag">29</span>
              <p>시험기간</p><span class="product-tag">2020-05-08~2020-09-08</span>
              <p>시험원</p><span class="product-tag">정은하, 이루리</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜마인즈랩<br>MINDsLab</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">FAST 대화형 AI v1.0<br>(FAST Conversation AI v1.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 58.78%</div>
            </div>
            <div class="product-description">
              챗봇과 상담원의 상담을 관리하는 콜센터 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2020.09.10</span>
              <p>시험번호</p><span class="product-tag">GS-A-20-186</span>
              <p>WD</p><span class="product-tag">30</span>
              <p>시험기간</p><span class="product-tag">2020-07-20~2020-08-28</span>
              <p>시험원</p><span class="product-tag">이공선, 박주영</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">주식회사 솔루게이트<br>Solugate Inc.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">지식기반 챗봇 솔루션 V1.x<br>(SGVA™ V1.x)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 57.28%</div>
            </div>
            <div class="product-description">
              메신저 웹 서비스를 통해 입력된 사용자 질의에 대해 응답을 지원하는 챗봇 서비스 프로그램
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2020.01.20</span>
              <p>시험번호</p><span class="product-tag">GS-B-19-247</span>
              <p>WD</p><span class="product-tag">8</span>
              <p>시험기간</p><span class="product-tag">2019-12-31~2020-01-10</span>
              <p>시험원</p><span class="product-tag">변은영, 김준태</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜페르소나에이아이<br>Persona AI Co., Ltd.<br>(구: ㈜페르소나시스템<br>Personasystem. Co., Ltd.)</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">페르소나 대화엔진 v1.0<br>(Persona Dialog Engine v1.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 66.59%</div>
            </div>
            <div class="product-description">
              텍스트로 입력된 사용자 질의에 자연어 처리 기반의 자동 응답을 지원하는 챗봇 서비스 프로그램
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2019.12.19</span>
              <p>시험번호</p><span class="product-tag">GS-A-19-327</span>
              <p>WD</p><span class="product-tag">14</span>
              <p>시험기간</p><span class="product-tag">2019-10-02~2019-12-10</span>
              <p>시험원</p><span class="product-tag">유화경, 이강민</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜스코인포<br>SKOINFO Co., Ltd.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">알에프씨 챗봇 v1.0<br>(RFC Chatbot v1.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 60.80%</div>
            </div>
            <div class="product-description">
              사용자로부터 입력된 질의와 DBMS에 사전 구축된 질의와의 유사도를 분석하여 답변을 제공하는 챗봇 프로그램
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2019.12.16</span>
              <p>시험번호</p><span class="product-tag">GS-A-19-338</span>
              <p>WD</p><span class="product-tag">12</span>
              <p>시험기간</p><span class="product-tag">2019-11-25~2019-12-10</span>
              <p>시험원</p><span class="product-tag">박상신, 김경준</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜아이액츠<br>iACTS CO., Ltd</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">대화형 검색로봇 시스템 v2.0<br>(SmartChat v2.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 55.79%</div>
            </div>
            <div class="product-description">
              SmartManager v2.0', 'SmartNet v3.0'과 연동하여 문자로(텍스트) 입력된 사용자 질의에 자동 응답을 지원하는 챗봇 서비스 프로그램
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2019.10.07</span>
              <p>시험번호</p><span class="product-tag">GS-C-19-068</span>
              <p>WD</p><span class="product-tag">13</span>
              <p>시험기간</p><span class="product-tag">2019-09-11~2019-10-01</span>
              <p>시험원</p><span class="product-tag">이재훈, 유수현</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜바이브컴퍼니<br>VAIV Company Inc.<br>(구: ㈜다음소프트<br>Daumsoft Inc.)</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">컨텍스츄얼 챗봇엔진 v5.0<br>(Contextual CA v5.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 67.33%</div>
            </div>
            <div class="product-description">
              메신저를 통해 입력된 사용자 질의에 자연어 처리 기반의 자동 응답을 지원하는 챗봇 서비스 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2019.06.24</span>
              <p>시험번호</p><span class="product-tag">GS-B-18-353</span>
              <p>WD</p><span class="product-tag">18</span>
              <p>시험기간</p><span class="product-tag">2019-03-19~2019-06-18</span>
              <p>시험원</p><span class="product-tag">우수진,조신원</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜메이팜소프트<br>Mayfarmsoft co.,Ltd.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">아이오스튜디오 Ver 1.0<br>(IO-STUDIO Ver 1.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 58.95%</div>
            </div>
            <div class="product-description">
              상담 시나리오 기반으로 채팅을 통해 사용자 질의에 대해 자동으로 답변해주는 채팅기반 상담 솔루션
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2019.03.21</span>
              <p>시험번호</p><span class="product-tag">GS-A-18-478</span>
              <p>WD</p><span class="product-tag">16</span>
              <p>시험기간</p><span class="product-tag">2019-02-19~2019-03-13</span>
              <p>시험원</p><span class="product-tag">구정회, 반지원</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜와이즈넛<br>WISEnut,Inc.</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">와이즈 아이챗 V2<br>(WISE i Chat V2)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 59.05%</div>
            </div>
            <div class="product-description">
              메신저 플랫폼과 연동하여 입력된 사용자 질의에 자동으로 응답해주는 챗봇 서비스 구축 프로그램
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2017.11.06</span>
              <p>시험번호</p><span class="product-tag">GS-A-17-224</span>
              <p>WD</p><span class="product-tag">12</span>
              <p>시험기간</p><span class="product-tag">2017-10-12~2017-10-27</span>
              <p>시험원</p><span class="product-tag">김유진, 천혜영</span>
            </div>
          </div>
        
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">㈜ 다이퀘스트<br>diquest Inc.<br>(구 : ㈜엔에이치엔다이퀘스트<br>NHN Diquest Inc.)<br>(구:㈜다이퀘스트<br>DIQUEST CO.LTD)</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">인포채터 v2.0<br>(Infochatter v2.0)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 57.04%</div>
            </div>
            <div class="product-description">
              채팅을 통해 내/외부 서비스와 연계한 정보 제공 및 제어 등이 가능하도록 지원하는 대화 에이전트 시스템
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">2017.03.13</span>
              <p>시험번호</p><span class="product-tag">GS-B-17-001</span>
              <p>WD</p><span class="product-tag">15</span>
              <p>시험기간</p><span class="product-tag">2017-02-10~2017-03-03</span>
              <p>시험원</p><span class="product-tag">장세헌, 이세인</span>
            </div>
          </div>
        </div>
        `;
        summaryContent.innerHTML = summaryhtml;
        resultsContent.innerHTML = resulthtml;
      }
    } catch (err) {
      resultsContent.innerHTML = `<span style="color:red;">에러: ${err.message}</span>`;
    } finally {
      hideLoading();
    }
  }, 3000);
});
