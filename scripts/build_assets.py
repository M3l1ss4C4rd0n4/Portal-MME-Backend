#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                         BUILD ASSETS SCRIPT                                   ║
║                                                                               ║
║  Script para optimizar assets del Portal Energético                          ║
║  - Minifica CSS                                                               ║
║  - Optimiza imágenes                                                          ║
║  - Genera versiones comprimidas                                               ║
║                                                                               ║
║  Uso:                                                                          ║
║     python scripts/build_assets.py                                            ║
║     python scripts/build_assets.py --watch                                    ║
║     python scripts/build_assets.py --production                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""
import os
import sys
import gzip
import shutil
import argparse
from pathlib import Path
from datetime import datetime

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def minify_css(input_file: Path, output_file: Path) -> dict:
    """
    Minifica un archivo CSS eliminando comentarios, espacios y saltos de línea.
    
    Args:
        input_file: Archivo CSS de entrada
        output_file: Archivo CSS minificado de salida
    
    Returns:
        Dict con estadísticas del proceso
    """
    content = input_file.read_text(encoding='utf-8')
    original_size = len(content)
    
    # Eliminar comentarios /* ... */
    import re
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    # Eliminar espacios al inicio y final de líneas
    content = '\n'.join(line.strip() for line in content.split('\n'))
    
    # Eliminar líneas vacías múltiples
    content = re.sub(r'\n{3,}', '\n\n', content)
    
    # Eliminar espacios después de : y ;
    content = re.sub(r':\s+', ':', content)
    content = re.sub(r';\s+', ';', content)
    
    # Eliminar espacios antes de { y }
    content = re.sub(r'\s+{', '{', content)
    content = re.sub(r'}\s+', '}', content)
    
    # Eliminar ; antes de }
    content = re.sub(r';}', '}', content)
    
    # Eliminar espacios múltiples
    content = re.sub(r'\s+', ' ', content)
    
    # Guardar archivo minificado
    output_file.write_text(content.strip(), encoding='utf-8')
    
    minified_size = len(content)
    savings = original_size - minified_size
    
    return {
        'original_size': original_size,
        'minified_size': minified_size,
        'savings': savings,
        'savings_percent': (savings / original_size * 100) if original_size > 0 else 0
    }


def compress_gzip(input_file: Path, output_file: Path = None) -> dict:
    """
    Comprime un archivo usando gzip.
    
    Args:
        input_file: Archivo a comprimir
        output_file: Archivo comprimido (opcional)
    
    Returns:
        Dict con estadísticas
    """
    if output_file is None:
        output_file = Path(str(input_file) + '.gz')
    
    original_size = input_file.stat().st_size
    
    with open(input_file, 'rb') as f_in:
        with gzip.open(output_file, 'wb', compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)
    
    compressed_size = output_file.stat().st_size
    savings = original_size - compressed_size
    
    return {
        'original_size': original_size,
        'compressed_size': compressed_size,
        'savings': savings,
        'savings_percent': (savings / original_size * 100) if original_size > 0 else 0
    }


def process_css_files(assets_dir: Path, production: bool = False) -> list:
    """
    Procesa todos los archivos CSS en el directorio de assets.
    
    Args:
        assets_dir: Directorio de assets
        production: Si es True, también genera versiones comprimidas
    
    Returns:
        Lista de resultados por archivo
    """
    css_dir = assets_dir / 'css'
    dist_dir = assets_dir / 'dist'
    dist_dir.mkdir(exist_ok=True)
    
    results = []
    
    for css_file in css_dir.glob('*.css'):
        print(f"\n📝 Procesando: {css_file.name}")
        
        # Archivo minificado
        minified_file = dist_dir / f"{css_file.stem}.min.css"
        
        try:
            # Minificar
            stats = minify_css(css_file, minified_file)
            
            print(f"   Original: {stats['original_size']:,} bytes")
            print(f"   Minificado: {stats['minified_size']:,} bytes")
            print(f"   Ahorro: {stats['savings_percent']:.1f}%")
            
            result = {
                'file': css_file.name,
                'minified': stats,
            }
            
            # Comprimir si es producción
            if production:
                gz_file = dist_dir / f"{css_file.stem}.min.css.gz"
                gzip_stats = compress_gzip(minified_file, gz_file)
                
                print(f"   Gzip: {gzip_stats['compressed_size']:,} bytes")
                print(f"   Ahorro total: {gzip_stats['savings_percent']:.1f}%")
                
                result['gzip'] = gzip_stats
            
            results.append(result)
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results.append({'file': css_file.name, 'error': str(e)})
    
    return results


def copy_critical_css(assets_dir: Path) -> None:
    """
    Copia los archivos CSS críticos al directorio dist para uso inmediato.
    
    Args:
        assets_dir: Directorio de assets
    """
    css_dir = assets_dir / 'css'
    dist_dir = assets_dir / 'dist'
    
    # Crear un bundle de todos los CSS
    bundle_content = []
    
    for css_file in sorted(css_dir.glob('*.css')):
        bundle_content.append(f"/* {css_file.name} */")
        bundle_content.append(css_file.read_text(encoding='utf-8'))
        bundle_content.append("")
    
    bundle_file = dist_dir / 'bundle.css'
    bundle_file.write_text('\n'.join(bundle_content), encoding='utf-8')
    print(f"\n📦 Bundle creado: {bundle_file}")
    
    # Minificar bundle
    bundle_min = dist_dir / 'bundle.min.css'
    minify_css(bundle_file, bundle_min)
    print(f"📦 Bundle minificado: {bundle_min}")


def print_summary(results: list) -> None:
    """
    Imprime un resumen del proceso de build.
    
    Args:
        results: Lista de resultados por archivo
    """
    print("\n" + "=" * 70)
    print("RESUMEN DE BUILD")
    print("=" * 70)
    
    total_original = 0
    total_minified = 0
    errors = 0
    
    for result in results:
        if 'error' in result:
            errors += 1
            continue
        
        total_original += result['minified']['original_size']
        total_minified += result['minified']['minified_size']
    
    print(f"\nArchivos procesados: {len(results)}")
    print(f"Errores: {errors}")
    print(f"\nTamaño original total: {total_original:,} bytes ({total_original/1024:.1f} KB)")
    print(f"Tamaño minificado total: {total_minified:,} bytes ({total_minified/1024:.1f} KB)")
    print(f"Ahorro total: {total_original - total_minified:,} bytes ({(1 - total_minified/total_original)*100:.1f}%)")
    print("=" * 70)


def main():
    """Función principal del script."""
    parser = argparse.ArgumentParser(
        description='Build script para optimizar assets del Portal Energético'
    )
    parser.add_argument(
        '--production', '-p',
        action='store_true',
        help='Modo producción (genera versiones comprimidas gzip)'
    )
    parser.add_argument(
        '--watch', '-w',
        action='store_true',
        help='Modo watch (recompila automáticamente al cambiar archivos)'
    )
    parser.add_argument(
        '--bundle', '-b',
        action='store_true',
        help='Crear bundle de todos los CSS'
    )
    
    args = parser.parse_args()
    
    # Directorio base
    base_dir = Path(__file__).parent.parent
    assets_dir = base_dir / 'assets'
    
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║              BUILD ASSETS - Portal Energético MME              ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print(f"\n📁 Directorio de assets: {assets_dir}")
    print(f"🕐 Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⚙️  Modo producción: {'Sí' if args.production else 'No'}")
    
    if args.watch:
        print("\n👀 Modo watch activado (Ctrl+C para detener)")
        try:
            while True:
                results = process_css_files(assets_dir, args.production)
                if args.bundle:
                    copy_critical_css(assets_dir)
                print_summary(results)
                print("\n⏳ Esperando cambios...")
                import time
                time.sleep(2)
        except KeyboardInterrupt:
            print("\n\n👋 Detenido por el usuario")
    else:
        results = process_css_files(assets_dir, args.production)
        if args.bundle:
            copy_critical_css(assets_dir)
        print_summary(results)
    
    print(f"\n🕐 Fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n✅ Build completado")


if __name__ == '__main__':
    main()
