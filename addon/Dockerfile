ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install Python and dependencies
RUN \
    apk add --no-cache \
    python3 \
    py3-pip \
    gcc \
    py3-pandas \
    py3-numpy \
    py3-scipy \
    py3-scikit-learn \
    py3-requests \
    py3-paho-mqtt

RUN pip3 install --no-cache-dir pymodbus --break-system-packages

# Copy files
COPY startup.sh /startup.sh
COPY full_forecast_and_reccomendation.py /app/full_forecast_and_reccomendation.py
COPY mqtt_discovery.py /app/mqtt_discovery.py

# Make scripts executable
RUN chmod +x /startup.sh

CMD ["/startup.sh"]
