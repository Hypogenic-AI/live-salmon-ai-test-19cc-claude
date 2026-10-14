# Image for running model-written analysis code. Versions match the repository's own
# environment (numpy, pandas, scipy, scikit-learn) plus statsmodels.
FROM python:3.12-slim
RUN pip install --no-cache-dir \
        numpy==2.4.3 pandas==3.0.1 scipy==1.17.1 scikit-learn==1.8.0 statsmodels==0.15.0
COPY runner.py /opt/runner.py
