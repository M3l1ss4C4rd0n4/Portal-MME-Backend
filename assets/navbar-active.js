/**
 * Script para manejar el estado activo del navbar
 * Se ejecuta después de cada navegación
 */

// Función para actualizar el link activo
function updateActiveNavLink() {
    // Obtener la ruta actual
    const currentPath = window.location.pathname;
    
    // Mapeo de rutas a IDs de links
    const routeMap = {
        '/': 'nav-link-inicio',
        '/generacion': 'nav-link-generacion',
        '/transmision': 'nav-link-transmision',
        '/distribucion': 'nav-link-distribucion',
        '/comercializacion': 'nav-link-comercializacion',
        '/perdidas': 'nav-link-perdidas',
        '/restricciones': 'nav-link-restricciones',
        '/metricas': 'nav-link-metricas'
    };
    
    // Remover clase 'active' de todos los links
    document.querySelectorAll('.navbar-link').forEach(link => {
        link.classList.remove('active');
    });
    
    // Agregar clase 'active' al link actual
    const activeLinkId = routeMap[currentPath];
    if (activeLinkId) {
        const activeLink = document.getElementById(activeLinkId);
        if (activeLink) {
            activeLink.classList.add('active');
        }
    }
}

// Ejecutar al cargar la página
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', updateActiveNavLink);
} else {
    updateActiveNavLink();
}

// Observer para detectar cambios en la URL (navegación Dash)
const observer = new MutationObserver(function(mutations) {
    updateActiveNavLink();
});

// Observar cambios en el contenido del page-container (indica navegación en Dash)
const pageContainer = document.getElementById('page-content');
if (pageContainer) {
    observer.observe(pageContainer, {
        childList: true,
        subtree: true
    });
}

// También escuchar eventos de navegación
window.addEventListener('popstate', updateActiveNavLink);

// Interceptar clicks en los links del navbar para actualizar inmediatamente
document.addEventListener('click', function(e) {
    if (e.target.closest('.navbar-link')) {
        setTimeout(updateActiveNavLink, 100);
    }
});
