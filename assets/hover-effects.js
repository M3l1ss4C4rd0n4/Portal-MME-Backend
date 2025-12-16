// Efectos hover para módulos de la portada - VERSION DEBUG
console.log('🔥 ARCHIVO JAVASCRIPT CARGADO');

document.addEventListener('DOMContentLoaded', function() {
    // ✅ SOLO EJECUTAR EN LA PORTADA
    const currentPath = window.location.pathname;
    if (currentPath !== '/' && !currentPath.includes('index')) {
        console.log('⏭️ Saltando hover-effects.js - No estamos en la portada (path:', currentPath, ')');
        return;
    }
    
    console.log('🚀 DOM LISTO - Inicializando efectos hover...');
    
    // Diagnóstico completo
    function diagnoseElements() {
        console.log('🔍 DIAGNÓSTICO COMPLETO:');
        
        // Buscar módulos
        const containers = document.querySelectorAll('.module-container');
        console.log('📦 Módulos con clase .module-container:', containers.length);
        containers.forEach((container, i) => {
            console.log(`   - Módulo ${i + 1}: ID="${container.id}", clase="${container.className}"`);
        });
        
        // Buscar por ID específicos
        const moduleIds = ['generacion', 'transmision', 'distribucion', 'metricas', 'restricciones', 'perdidas'];
        moduleIds.forEach(id => {
            const moduleElement = document.getElementById(`module-${id}`);
            const tooltipElement = document.getElementById(`tooltip-${id}`);
            console.log(`🎯 module-${id}: ${moduleElement ? 'ENCONTRADO' : 'NO ENCONTRADO'}`);
            console.log(`💬 tooltip-${id}: ${tooltipElement ? 'ENCONTRADO' : 'NO ENCONTRADO'}`);
        });
        
        // Buscar SVG
        const svgBackground = document.querySelector('img[src="/assets/portada.svg"]');
        console.log('🖼️ SVG de fondo:', svgBackground ? 'ENCONTRADO' : 'NO ENCONTRADO');
        
        // Buscar todos los elementos con IDs que empiecen con 'module-'
        const allModules = document.querySelectorAll('[id^="module-"]');
        console.log('� Todos los elementos con ID module-*:', allModules.length);
        
        // Buscar todos los elementos con IDs que empiecen con 'tooltip-'
        const allTooltips = document.querySelectorAll('[id^="tooltip-"]');
        console.log('� Todos los elementos con ID tooltip-*:', allTooltips.length);
        
        return { containers, svgBackground, allModules, allTooltips };
    }
    
    // Esperar un poco y luego diagnosticar
    setTimeout(function() {
        const { containers, svgBackground, allModules, allTooltips } = diagnoseElements();
        
        if (containers.length === 0 && allModules.length === 0) {
            console.error('❌ NO SE ENCONTRARON MÓDULOS. Reintentando en 2 segundos...');
            setTimeout(diagnoseElements, 2000);
            return;
        }
        
        // Usar los módulos encontrados (prioritariamente por clase, luego por ID)
        const modulesToUse = containers.length > 0 ? containers : allModules;
        
        console.log(`✅ Configurando eventos para ${modulesToUse.length} módulos`);
        
        modulesToUse.forEach(function(container, index) {
            console.log(`⚙️ Configurando módulo ${index + 1}: ${container.id}`);
            
            // Obtener el ID del módulo
            let moduleId = '';
            if (container.id && container.id.startsWith('module-')) {
                moduleId = container.id.replace('module-', '');
            } else {
                console.warn(`⚠️ Módulo ${index + 1} no tiene ID correcto:`, container.id);
                return;
            }
            
            const tooltip = document.getElementById('tooltip-' + moduleId);
            
            if (!tooltip) {
                console.warn(`⚠️ No se encontró tooltip para módulo ${moduleId}`);
            }
            
            // Evento HOVER IN
            container.addEventListener('mouseenter', function(e) {
                console.log(`🎯 HOVER IN en módulo: ${moduleId}`);
                e.preventDefault();
                
                // Buscar el overlay correspondiente
                const overlay = document.getElementById('overlay-' + moduleId);
                
                // Mostrar overlay oscuro con blur
                if (overlay) {
                    overlay.style.opacity = '1';
                    overlay.style.visibility = 'visible';
                    console.log('🌑 Overlay oscuro mostrado');
                }
                
                // Oscurecer otros módulos
                modulesToUse.forEach(function(otherContainer) {
                    if (otherContainer !== container) {
                        otherContainer.style.filter = 'brightness(0.3)';
                        otherContainer.style.opacity = '0.4';
                        otherContainer.style.transition = 'all 0.4s ease';
                    }
                });
                console.log('🌑 Otros módulos oscurecidos');
                
                // Iluminar módulo actual (brillo + sombra amarilla)
                container.style.filter = 'brightness(1.5) saturate(1.5) drop-shadow(0 0 30px rgba(255, 193, 7, 0.8))';
                container.style.transform = 'scale(1.1)';
                container.style.zIndex = '50';
                container.style.transition = 'all 0.4s ease';
                console.log('✨ Módulo actual iluminado');
                
                // Mostrar tooltip
                if (tooltip) {
                    tooltip.style.opacity = '1';
                    tooltip.style.visibility = 'visible';
                    tooltip.style.transform = 'translate(-50%, -50%) scale(1)';
                    tooltip.style.transition = 'all 0.4s ease';
                    console.log(`💬 Tooltip ${moduleId} mostrado`);
                } else {
                    console.warn(`⚠️ No se pudo mostrar tooltip para ${moduleId}`);
                }
            });
            
            // Evento HOVER OUT
            container.addEventListener('mouseleave', function(e) {
                console.log(`🎯 HOVER OUT en módulo: ${moduleId}`);
                e.preventDefault();
                
                // Buscar el overlay correspondiente
                const overlay = document.getElementById('overlay-' + moduleId);
                
                // Ocultar overlay oscuro
                if (overlay) {
                    overlay.style.opacity = '0';
                    overlay.style.visibility = 'hidden';
                    console.log('🌕 Overlay oscuro oculto');
                }
                
                // Restaurar todos los módulos (NO tocar portada_secciones.png)
                modulesToUse.forEach(function(otherContainer) {
                    otherContainer.style.filter = 'drop-shadow(0 4px 10px rgba(0, 0, 0, 0.3))';
                    otherContainer.style.opacity = '1';
                    otherContainer.style.transform = 'scale(1)';
                    otherContainer.style.zIndex = '10';
                    otherContainer.style.transition = 'all 0.4s ease';
                });
                
                // Ocultar tooltip
                if (tooltip) {
                    tooltip.style.opacity = '0';
                    tooltip.style.visibility = 'hidden';
                    tooltip.style.transform = 'translate(-50%, -50%) scale(0.9)';
                    tooltip.style.transition = 'all 0.4s ease';
                }
                
                console.log(`🔄 Todo restaurado para ${moduleId}`);
            });
        });
        
        console.log('✅ TODOS LOS EVENTOS CONFIGURADOS CORRECTAMENTE');
    }, 1000); // Esperamos 1 segundo para que todo cargue
});