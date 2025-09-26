// 스크롤 애니메이션 및 인터랙션 스크립트

document.addEventListener('DOMContentLoaded', function() {
    // 요소들 선택
    const contentSection = document.querySelector('.content-section');
    const sectionContainers = document.querySelectorAll('.section-container');
    const cards = document.querySelectorAll('.card');
    const scrollIndicator = document.querySelector('.scroll-indicator');

    // 스크롤 이벤트 리스너
    window.addEventListener('scroll', function() {
        const scrollTop = window.pageYOffset;
        const windowHeight = window.innerHeight;
        
        // 스크롤 인디케이터 숨기기
        if (scrollTop > windowHeight * 0.1) {
            scrollIndicator.style.opacity = '0';
            scrollIndicator.style.transform = 'translateX(-50%) translateY(20px)';
        } else {
            scrollIndicator.style.opacity = '1';
            scrollIndicator.style.transform = 'translateX(-50%) translateY(0)';
        }

        // 컨텐츠 섹션 애니메이션
        const contentSectionTop = contentSection.offsetTop;
        if (scrollTop + windowHeight > contentSectionTop + 200) {
            contentSection.classList.add('visible');
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
    scrollIndicator.addEventListener('click', function() {
        const contentSectionTop = contentSection.offsetTop;
        window.scrollTo({
            top: contentSectionTop,
            behavior: 'smooth'
        });
    });

    // 카드 클릭 이벤트
    cards.forEach(card => {
        card.addEventListener('click', function() {
            const title = this.querySelector('.card-title').textContent.trim();
            
            // 클릭 효과
            this.style.transform = 'scale(0.95)';
            setTimeout(() => {
                this.style.transform = '';
            }, 150);

            // 알림 (실제 서비스에서는 해당 기능 페이지로 이동)
            showNotification(`"${title}" 기능을 선택하셨습니다.`);
        });

        // 카드 호버 효과 개선
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-10px) scale(1.02)';
        });

        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0) scale(1)';
        });
    });



    // 알림 표시 함수
    function showNotification(message) {
        // 기존 알림 제거
        const existingNotification = document.querySelector('.notification');
        if (existingNotification) {
            existingNotification.remove();
        }

        // 새 알림 생성
        const notification = document.createElement('div');
        notification.className = 'notification';
        notification.textContent = message;
        
        // 알림 스타일
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

        // 애니메이션으로 표시
        setTimeout(() => {
            notification.style.opacity = '1';
            notification.style.transform = 'translateX(0)';
        }, 10);

        // 3초 후 자동 제거
        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, 300);
        }, 3000);
    }

    // 부드러운 스크롤 개선
    function smoothScrollTo(target, duration = 1000) {
        const targetPosition = target.offsetTop;
        const startPosition = window.pageYOffset;
        const distance = targetPosition - startPosition;
        let startTime = null;

        function animation(currentTime) {
            if (startTime === null) startTime = currentTime;
            const timeElapsed = currentTime - startTime;
            const run = ease(timeElapsed, startPosition, distance, duration);
            window.scrollTo(0, run);
            if (timeElapsed < duration) requestAnimationFrame(animation);
        }

        function ease(t, b, c, d) {
            t /= d / 2;
            if (t < 1) return c / 2 * t * t + b;
            t--;
            return -c / 2 * (t * (t - 2) - 1) + b;
        }

        requestAnimationFrame(animation);
    }

    // Intersection Observer for better performance
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, observerOptions);

    // Observe all animatable elements
    sectionContainers.forEach(container => {
        observer.observe(container);
    });

    // 초기 스크롤 위치에 따른 애니메이션 트리거
    window.dispatchEvent(new Event('scroll'));

    // 페이지 로드 완료 후 hero 섹션 애니메이션 시작
    setTimeout(() => {
        document.querySelector('.hero-content').style.opacity = '1';
    }, 100);

    // 키보드 네비게이션 지원
    document.addEventListener('keydown', function(e) {
        if (e.key === 'ArrowDown' && window.pageYOffset < window.innerHeight) {
            e.preventDefault();
            smoothScrollTo(contentSection);
        } else if (e.key === 'ArrowUp' && window.pageYOffset > window.innerHeight) {
            e.preventDefault();
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        }
    });

    console.log('TTA AI ON - GS인증 업무 자동화 시스템이 로드되었습니다.');
});
