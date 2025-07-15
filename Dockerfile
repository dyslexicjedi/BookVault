FROM python:3

WORKDIR /usr/src/app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY helpers.py .
COPY api_blueprint.py .
ADD templates /usr/src/app/templates/
ADD static /usr/src/app/static/

CMD ["python","./app.py"]