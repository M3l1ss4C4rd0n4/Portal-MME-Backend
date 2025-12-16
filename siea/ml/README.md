# ML - Modelos Predictivos

Modelos de machine learning para pronóstico de demanda, precios y pérdidas.

## Modelos Implementados

### 1. Demanda Eléctrica
- **Algoritmo**: Prophet / LSTM
- **Horizonte**: 7 días
- **Features**: demanda histórica, temperatura, día de la semana, festivos
- **Métricas objetivo**: RMSE < 5% del promedio

### 2. Precio Bolsa
- **Algoritmo**: ARIMA + variables exógenas
- **Horizonte**: Siguiente hora
- **Features**: demanda, generación térmica/hidro, precio histórico
- **Métricas objetivo**: MAE < $10 COP/kWh

### 3. Pérdidas Técnicas
- **Algoritmo**: XGBoost Classifier
- **Salida**: Scoring de riesgo por OR (1-5)
- **Features**: histórico pérdidas, ubicación, infraestructura
- **Métricas objetivo**: AUC-ROC > 0.75

## Estructura

```
ml/
├── models/                 # Modelos entrenados (.pkl, .pth)
│   ├── demanda_prophet.pkl
│   ├── precio_arima.pkl
│   └── perdidas_xgboost.pkl
├── training/              # Scripts de entrenamiento
│   ├── train_demanda.py
│   ├── train_precio.py
│   └── train_perdidas.py
├── inference/             # Scripts de inferencia
│   ├── predict_demanda.py
│   ├── predict_precio.py
│   └── predict_perdidas.py
├── evaluation/            # Evaluación y métricas
│   ├── metrics.py
│   └── reports/
├── mlflow_tracking/       # Experimentos MLflow
└── requirements.txt
```

## Instalación

```bash
cd ml
pip install -r requirements.txt
```

## Entrenamiento

```bash
# Entrenar modelo de demanda
python training/train_demanda.py --data ../data/processed/demanda.parquet --output models/

# Con MLflow tracking
mlflow run training/ -P model=demanda
```

## Inferencia

```bash
python inference/predict_demanda.py --model models/demanda_prophet.pkl --horizon 7
```

## MLflow UI

```bash
mlflow ui --backend-store-uri sqlite:///mlflow_tracking/mlflow.db
# http://localhost:5000
```

## Reentrenamiento

- Incremental: Diario (append nuevos datos)
- Completo: Semanal (refit desde cero)
- Evaluación: Backtesting con ventana deslizante
