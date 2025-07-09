FROM python:3

WORKDIR /usr/src/app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
ADD folder /usr/src/app/templates
COPY templates /usr/src/app/templates/

CMD ["python","./app.py"]