FROM golang:buster

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    git \
 && rm -rf /var/lib/apt/lists/*

RUN pip3 install paho-mqtt typing-extensions

RUN git clone https://github.com/bemasher/rtlamr.git /go/src/github.com/bemasher/rtlamr
WORKDIR /go/src/github.com/bemasher/rtlamr
RUN go install

ADD metermon-ha.py .

CMD ["python3", "-u", "./metermon-ha.py"]
