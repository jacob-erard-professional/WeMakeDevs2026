# Makes the start-local Elasticsearch container reachable from pods as
# http://elasticsearch:9200. Rendered by scripts/dev-up.sh with the container IP.
apiVersion: v1
kind: Service
metadata:
  name: elasticsearch
spec:
  ports:
    - name: http
      port: 9200
      targetPort: 9200
---
apiVersion: discovery.k8s.io/v1
kind: EndpointSlice
metadata:
  name: elasticsearch-start-local
  labels:
    kubernetes.io/service-name: elasticsearch
addressType: IPv4
ports:
  - name: http
    port: 9200
    protocol: TCP
endpoints:
  - addresses:
      - "${ES_IP}"
