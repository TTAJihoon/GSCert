// 스크롤 애니메이션 및 인터랙션 스크립트 (자동 스크롤 후 자유 스크롤 복구 버전)

document.addEventListener('DOMContentLoaded', function() {
    // 요소들 선택
    const contentSection = document.querySelector('.content-section');
    const sectionContainers = document.querySelectorAll('.section-container');
    const cards = document.querySelectorAll('.card');
    const scrollIndicator = document.querySelector('.scroll-indicator');

    // 내부 상태
    let autoScrollTimer = null;
    let autoScrolling = false;   // 자동 스크롤 진행 중 플래그
    let rafId = null;            // requestAnimationFrame id

    // [중요] 스크롤 잠금용 공용 핸들러(같은 참조 유지)
    const preventScrollHandler = (e) => {
        if (e.type === 'keydown') {
            const blockKeys = ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '];
            if (blockKeys.includes(e.key)) e.preventDefault();
            return;
        }
        e.preventDefault();
    };

    // 스크롤 잠금/해제
    const passiveFalse = { passive: false };
    function lockScroll(enable) {
        if (enable) {
            window.addEventListener('wheel', preventScrollHandler, passiveFalse);
            window.addEventListener('touchmove', preventScrollHandler, passiveFalse);
            document.addEventListener('keydown', preventScrollHandler, passiveFalse);
        } else {
            window.removeEventListener('wheel', preventScrollHandler, passiveFalse);
            window.removeEventListener('touchmove', preventScrollHandler, passiveFalse);
            document.removeEventListener('keydown', preventScrollHandler, passiveFalse);
        }
    }

    // 스크롤 이벤트 리스너
    window.addEventListener('scroll', function() {
        const scrollTop = window.pageYOffset;
        const windowHeight = window.innerHeight;
        
        // 스크롤 인디케이터 숨기기
        if (scrollIndicator) {
            if (scrollTop > windowHeight * 0.1) {
                scrollIndicator.style.opacity = '0';
                scrollIndicator.style.transform = 'translateX(-50%) translateY(20px)';
            } else {
                scrollIndicator.style.opacity = '1';
                scrollIndicator.style.transform = 'translateX(-50%) translateY(0)';
            }
        }

        // 컨텐츠 섹션 애니메이션
        if (contentSection) {
            const contentSectionTop = contentSection.offsetTop;
            if (scrollTop + windowHeight > contentSectionTop + 200) {
                contentSection.classList.add('visible');
            }
        }

        // 개별 섹션 컨테이너 애니메이션
        sectionContainers.forEach((container, index) => {
            const containerTop = container.offsetTop;
            if (scrollTop + windowHeight > containerTop + 100) {
                setTimeout(() => {
                    container.classList.add('visible');
                }, index * 200); // 순차적으로 나타나게 함
            }
        });

        // 카드 애니메이션
        cards.forEach((card, index) => {
            const cardTop = card.offsetTop;
            const cardParent = card.closest('.section-container');
            if (cardParent && cardParent.classList.contains('visible')) {
                if (scrollTop + windowHeight > cardTop + 50) {
                    setTimeout(() => {
                        card.style.opacity = '1';
                        card.style.transform = 'translateY(0)';
                    }, (index % 4) * 100); // 각 섹션 내에서 순차적으로 나타남
                }
            }
        });
    });

    // 카드 초기 상태 설정
    cards.forEach(card => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(30px)';
        card.style.transition = 'all 0.6s ease-out';
    });

    // 스크롤 인디케이터 클릭 이벤트
    if (scrollIndicator && contentSection) {
        scrollIndicator.addEventListener('click', function() {
            window.scrollTo({ top: contentSection.offsetTop, behavior: 'smooth' });
        });
    }

    // 카드 클릭 이벤트
    cards.forEach(card => {
        card.addEventListener('click', function() {
            const title = this.querySelector('.card-title')?.textContent.trim() || '선택한 기능';
            this.style.transform = 'scale(0.95)';
            setTimeout(() => { this.style.transform = ''; }, 150);
            showNotification(`"${title}" 기능을 선택하셨습니다.`);
        });
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-10px) scale(1.02)';
        });
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0) scale(1)';
        });
    });

    // 알림 표시 함수
    function showNotification(message) {
        const existingNotification = document.querySelector('.notification');
        if (existingNotification) existingNotification.remove();

        const notification = document.createElement('div');
        notification.className = 'notification';
        notification.textContent = message;

        Object.assign(notification.style, {
            position: 'fixed',
            top: '20px',
            right: '20px',
            backgroundColor: '#4299e1',
            color: 'white',
            padding: '15px 25px',
            borderRadius: '8px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            zIndex: '9999',
            fontSize: '14px',
            fontWeight: '500',
            opacity: '0',
            transform: 'translateX(100%)',
            transition: 'all 0.3s ease-out'
        });

        document.body.appendChild(notification);
        setTimeout(() => {
            notification.style.opacity = '1';
            notification.style.transform = 'translateX(0)';
        }, 10);
        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transform = 'translateX(100%)';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    // 부드러운 스크롤 (진행 중이면 새 호출이 덮어씀)
    function smoothScrollTo(target, duration = 1000) {
        if (!target) return;
        if (rafId) cancelAnimationFrame(rafId);

        const targetPosition = target.offsetTop;
        const startPosition = window.pageYOffset;
        const distance = targetPosition - startPosition;
        let startTime = null;

        // 네이티브 smooth와 충돌 방지
        const html = document.documentElement;
        const prevBehavior = html.style.scrollBehavior;
        html.style.scrollBehavior = 'auto';

        autoScrolling = true;
        lockScroll(true); // 자동 스크롤 동안 수동 스크롤 차단

        function animation(currentTime) {
            if (startTime === null) startTime = currentTime;
            const timeElapsed = currentTime - startTime;
            const run = ease(timeElapsed, startPosition, distance, duration);
            window.scrollTo(0, run);
            if (timeElapsed < duration) {
                rafId = requestAnimationFrame(animation);
            } else {
                // 종료 정리: 잠금 해제 + 상태 복구 (여기가 핵심)
                window.scrollTo(0, targetPosition);
                autoScrolling = false;
                lockScroll(false);             // ← 스크롤 해제 확실히 수행
                html.style.scrollBehavior = prevBehavior || '';
                rafId = null;
            }
        }

        function ease(t, b, c, d) {
            t /= d / 2;
            if (t < 1) return c / 2 * t * t + b;
            t--;
            return -c / 2 * (t * (t - 2) - 1) + b;
        }

        rafId = requestAnimationFrame(animation);
    }

    // Intersection Observer for better performance
    const observerOptions = { threshold: 0.1, rootMargin: '0px 0px -50px 0px' };
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => { if (entry.isIntersecting) entry.target.classList.add('visible'); });
    }, observerOptions);

    sectionContainers.forEach(container => observer.observe(container));

    // 초기 스크롤 위치에 따른 애니메이션 트리거
    window.dispatchEvent(new Event('scroll'));

    // 페이지 로드 완료 후 hero 섹션 애니메이션 시작
    setTimeout(() => {
        const hero = document.querySelector('.hero-content');
        if (hero) hero.style.opacity = '1';
    }, 100);

    // 모든 리소스 로딩 완료 후 1초 뒤 자동으로 콘텐츠 섹션으로 강제 스크롤
    window.addEventListener('load', () => {
        autoScrollTimer = setTimeout(() => {
            // 가시화 선행 처리(깜빡임 방지)
            contentSection?.classList.add('visible');
            sectionContainers.forEach(c => c.classList.add('visible'));
            cards.forEach(card => {
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            });
            // 강제 덮어쓰기 스크롤 실행
            if (contentSection) smoothScrollTo(contentSection, 800);
        }, 1000);
    });

    // 키보드 네비게이션 (자동 스크롤 중이면 입력 무시됨)
    document.addEventListener('keydown', function(e) {
        if (autoScrolling) return;
        if (e.key === 'ArrowDown' && window.pageYOffset < window.innerHeight) {
            e.preventDefault();
            smoothScrollTo(contentSection);
        } else if (e.key === 'ArrowUp' && window.pageYOffset > window.innerHeight) {
            e.preventDefault();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    });

    console.log('TTA AI ON - GS인증 업무 자동화 시스템이 로드되었습니다.');
});
