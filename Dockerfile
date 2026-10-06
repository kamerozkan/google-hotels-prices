FROM apify/actor-python:3.12

COPY requirements.txt ./

RUN echo "Python version:" \
 && python --version \
 && pip install --no-cache-dir -r requirements.txt \
 && pip freeze

COPY . ./

RUN python3 -m compileall -q src/

CMD ["python3", "-m", "src"]
