// Interactividad mejorada para la portada SVG
document.addEventListener('DOMContentLoaded', function() {
    // ✅ SOLO EJECUTAR EN LA PORTADA
    const currentPath = window.location.pathname;
    if (currentPath !== '/' && !currentPath.includes('index')) {
        console.log('⏭️ Saltando portada-interactive.js - No estamos en la portada (path:', currentPath, ')');
        return;
    }
    
    // Agregar efecto de parallax suave al mover el mouse
    const portadaContainer = document.querySelector('.hero-section');
    if (portadaContainer) {
        portadaContainer.addEventListener('mousemove', function(e) {
            const hotspots = document.querySelectorAll('.hotspot-link');
            const mouseX = e.clientX / window.innerWidth;
            const mouseY = e.clientY / window.innerHeight;
            
            hotspots.forEach((hotspot, index) => {
                const speed = (index + 1) * 0.5;
                const x = (mouseX - 0.5) * speed;
                const y = (mouseY - 0.5) * speed;
                
                // Aplicar transformación sutil sin interferir con el hover
                if (!hotspot.matches(':hover')) {
                    const area = hotspot.querySelector('.hotspot-area');
                    if (area) {
                        area.style.transform = `translate(${x}px, ${y}px)`;
                    }
                }
            });
        });
        
        // Resetear al salir
        portadaContainer.addEventListener('mouseleave', function() {
            const hotspots = document.querySelectorAll('.hotspot-area');
            hotspots.forEach(area => {
                area.style.transform = '';
            });
        });
    }
    
    // Agregar sonidos de interacción (opcional - comentado por defecto)
    /*
    const hotspotLinks = document.querySelectorAll('.hotspot-link');
    hotspotLinks.forEach(link => {
        link.addEventListener('mouseenter', function() {
            // Aquí se puede agregar un sonido de hover
            // new Audio('/assets/sounds/hover.mp3').play();
        });
        
        link.addEventListener('click', function() {
            // Aquí se puede agregar un sonido de click
            // new Audio('/assets/sounds/click.mp3').play();
        });
    });
    */
    
    // ===== MANEJO DEL MODAL DE INFORMACIÓN GENERAL (CU) =====
    // Usar un pequeño delay para asegurar que Dash haya renderizado todo
    setTimeout(function() {
        const infoButton = document.getElementById('info-button');
        const infoModal = document.getElementById('info-modal');
        const closeInfoButton = document.getElementById('close-info-button');
        
        console.log('Buscando elementos del modal:', {
            infoButton: !!infoButton,
            infoModal: !!infoModal,
            closeInfoButton: !!closeInfoButton
        });
        
        if (infoButton && infoModal) {
            const modalOverlay = infoModal.querySelector('div');
            
            infoButton.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                if (modalOverlay) {
                    modalOverlay.style.display = 'flex';
                    console.log('✅ Modal de información CU abierto');
                } else {
                    console.error('❌ No se encontró el overlay del modal');
                }
            });
            
            if (closeInfoButton) {
                closeInfoButton.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (modalOverlay) {
                        modalOverlay.style.display = 'none';
                        console.log('✅ Modal de información CU cerrado');
                    }
                });
            }
            
            // Cerrar modal al hacer clic fuera del contenido
            if (modalOverlay) {
                modalOverlay.addEventListener('click', function(e) {
                    if (e.target === this) {
                        this.style.display = 'none';
                        console.log('✅ Modal cerrado al hacer clic fuera');
                    }
                });
            }
            
            console.log('✅ Event listeners del modal configurados correctamente');
        } else {
            console.error('❌ No se encontraron todos los elementos del modal');
        }
    }, 1000);  // Delay de 1 segundo para asegurar que Dash haya renderizado

    
    // Agregar partículas flotantes en el fondo
    function createFloatingParticles() {
        const container = document.querySelector('[style*="100vh"]');
        if (!container) return;
        
        for (let i = 0; i < 15; i++) {
            const particle = document.createElement('div');
            particle.className = 'floating-particle';
            particle.style.cssText = `
                position: absolute;
                width: ${Math.random() * 4 + 2}px;
                height: ${Math.random() * 4 + 2}px;
                background: radial-gradient(circle, rgba(59, 130, 246, 0.6), transparent);
                border-radius: 50%;
                left: ${Math.random() * 100}%;
                top: ${Math.random() * 100}%;
                animation: float ${Math.random() * 10 + 10}s linear infinite;
                pointer-events: none;
                opacity: ${Math.random() * 0.5 + 0.2};
            `;
            container.appendChild(particle);
        }
    }
    
    // Crear partículas flotantes
    setTimeout(createFloatingParticles, 500);
    
    // Ocultar tooltip de bienvenida después de 5 segundos
    setTimeout(function() {
        const welcomeTooltip = document.getElementById('welcome-tooltip');
        if (welcomeTooltip) {
            welcomeTooltip.style.display = 'none';
        }
    }, 5000);
    
    console.log('✅ Portada interactiva cargada');
});

// Animación CSS para partículas flotantes
const style = document.createElement('style');
style.textContent = `
    @keyframes float {
        0% {
            transform: translateY(0) translateX(0) scale(1);
            opacity: 0;
        }
        10% {
            opacity: 0.8;
        }
        90% {
            opacity: 0.8;
        }
        100% {
            transform: translateY(-100vh) translateX(${Math.random() * 100 - 50}px) scale(0);
            opacity: 0;
        }
    }
    
    .floating-particle {
        filter: blur(1px);
    }
`;
document.head.appendChild(style);
