FROM golang:buster as builder

# Install OS packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    git \
 && rm -rf /var/lib/apt/lists/*

# Install Python packages.
RUN pip3 install paho-mqtt typing-extensions

# Clone rtlamr
RUN git clone https://github.com/bemasher/rtlamr.git /go/src/github.com/bemasher/rtlamr
WORKDIR /go/src/github.com/bemasher/rtlamr
RUN go install

# Add source files. Note that we add this *after* the go install
# of rtlamr. This allows us to take advantage of Docker's build cache
# so that rtlamr is only recompiled when there are changes to rtlamr,
# not when there are changes to our source code.
ADD metermon-ha.py .  #  <-- CHANGED THIS LINE

# Run metermon.
ENTRYPOINT [ "python3", "metermon-ha.py" ]  # <-- AND THIS LINE
