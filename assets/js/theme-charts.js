/**
 * Theme Charts Manager
 * Sincroniza automáticamente los gráficos Plotly con el tema oscuro/claro
 */

(function() {
    'use strict';

    // Configuración de colores para cada tema
    const CHART_THEMES = {
        light: {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#111827' },
            xaxis: {
                gridcolor: '#e5e7eb',
                linecolor: '#374151',
                tickfont: { color: '#374151' }
            },
            yaxis: {
                gridcolor: '#e5e7eb',
                linecolor: '#374151',
                tickfont: { color: '#374151' }
            },
            legend: {
                bgcolor: 'rgba(255,255,255,0.9)',
                font: { color: '#111827' }
            }
        },
        dark: {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#f1f5f9' },
            xaxis: {
                gridcolor: '#334155',
                linecolor: '#94a3b8',
                tickfont: { color: '#94a3b8' }
            },
            yaxis: {
                gridcolor: '#334155',
                linecolor: '#94a3b8',
                tickfont: { color: '#94a3b8' }
            },
            legend: {
                bgcolor: 'rgba(15,23,42,0.9)',
                font: { color: '#f1f5f9' }
            }
        }
    };

    /**
     * Obtiene el tema actual del documento
     */
    function getCurrentTheme() {
        return document.documentElement.getAttribute('data-theme') || 'light';
    }

    /**
     * Aplica el tema a un gráfico Plotly específico
     */
    function applyThemeToChart(chartElement, theme) {
        if (!chartElement || !window.Plotly) return;

        const themeConfig = CHART_THEMES[theme];
        if (!themeConfig) return;

        try {
            // Actualizar layout del gráfico
            window.Plotly.relayout(chartElement, {
                paper_bgcolor: themeConfig.paper_bgcolor,
                plot_bgcolor: themeConfig.plot_bgcolor,
                font: themeConfig.font,
                xaxis: themeConfig.xaxis,
                yaxis: themeConfig.yaxis,
                legend: themeConfig.legend
            });
        } catch (e) {
            console.warn('Error al aplicar tema al gráfico:', e);
        }
    }

    /**
     * Aplica el tema a todos los gráficos visibles
     */
    function applyThemeToAllCharts() {
        const theme = getCurrentTheme();
        const charts = document.querySelectorAll('.js-plotly-plot');
        
        charts.forEach(chart => {
            applyThemeToChart(chart, theme);
        });
    }

    /**
     * Observa cambios en el atributo data-theme
     */
    function observeThemeChanges() {
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.attributeName === 'data-theme') {
                    // Pequeño delay para asegurar que el CSS se haya aplicado
                    setTimeout(applyThemeToAllCharts, 100);
                }
            });
        });

        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ['data-theme']
        });
    }

    /**
     * Observa nuevos gráficos agregados al DOM
     */
    function observeNewCharts() {
        const observer = new MutationObserver((mutations) => {
            let hasNewCharts = false;
            
            mutations.forEach((mutation) => {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        if (node.classList && node.classList.contains('js-plotly-plot')) {
                            hasNewCharts = true;
                        }
                        // También buscar dentro del nodo agregado
                        if (node.querySelector && node.querySelector('.js-plotly-plot')) {
                            hasNewCharts = true;
                        }
                    }
                });
            });

            if (hasNewCharts) {
                setTimeout(() => {
                    applyThemeToAllCharts();
                }, 500); // Delay mayor para permitir que Plotly inicialice
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    /**
     * Inicializa el manejador de temas para gráficos
     */
    function init() {
        // Esperar a que Plotly esté disponible
        if (typeof window.Plotly === 'undefined') {
            setTimeout(init, 500);
            return;
        }

        // Aplicar tema inicial
        setTimeout(applyThemeToAllCharts, 1000);

        // Observar cambios de tema
        observeThemeChanges();

        // Observar nuevos gráficos
        observeNewCharts();

        console.log('[ThemeCharts] Inicializado');
    }

    // Iniciar cuando el DOM esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Exponer función global para uso manual
    window.updateChartThemes = applyThemeToAllCharts;

})();
