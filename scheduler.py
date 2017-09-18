#!/usr/bin/env python

import json

from kubernetes import client, config, watch
from sdcclient import SdcClient


config.load_kube_config()
v1 = client.CoreV1Api()
# Metric name as shown in Sysdig Monitor
metric_id = "net.http.request.time"
# Sysdig Monitor API Token
sdclient = SdcClient("c30a0cfd-609a-41a6-b822-e8e0d4bdeb0d")
# Time and group aggregations
metrics = [{"id": metric_id, "aggregations":
           {"time": "timeAvg", "group": "avg"}}]
# Nodes excluded from the scheduler
node_blacklist = ["kubemaster"]

# This is the string that you will need on the pod specs
scheduler_name = "sysdigsched"


def get_request_time(hostname):
    hostfilter = "host.hostName = '%s'" % hostname
    # Sample over the last 60 seconds, just one sample for this period
    metricdata = sdclient.get_data(metrics, -60, 0, 60, hostfilter)
    request_time = float(metricdata[1].get("data")[0].get("d")[0])
    print hostname + " (" + metric_id + "): " + str(request_time)
    return request_time


def best_request_time(nodes):
    if not nodes:
        return []
    node_times = [get_request_time(hostname) for hostname in nodes]
    best = nodes[node_times.index(min(node_times))]
    print "best node: " + best
    return best


def nodes_available():
    ready_nodes = []
    for n in v1.list_node().items:
            if n.metadata.name in node_blacklist:
                continue
            for status in n.status.conditions:
                # All Ready & not blacklisted nodes
                if status.status == "True" and status.type == "Ready":
                    ready_nodes.append(n.metadata.name)
    print "Nodes available: " + str(ready_nodes)
    return ready_nodes


# Binding the pod with the target node
def scheduler(name, node, namespace="default"):
    body = client.V1Binding()
    target = client.V1ObjectReference()
    target.kind = "Node"
    target.apiVersion = "v1"
    target.name = node

    meta = client.V1ObjectMeta()
    meta.name = name

    body.target = target
    body.metadata = meta

    return v1.create_namespaced_binding(namespace, body)


def main():
    w = watch.Watch()
    for event in w.stream(v1.list_namespaced_pod, "default"):
        # New pending pod that requires our custom scheduler
        if event["object"].status.phase == "Pending" and \
           event["object"].spec.scheduler_name == scheduler_name and not \
           event["object"].spec.node_name:
            try:
                # Choose the best target node using Sysdig metrics
                res = scheduler(event["object"].metadata.name,
                                best_request_time(nodes_available()))
            except client.rest.ApiException as e:
                print json.loads(e.body)["message"]

if __name__ == "__main__":
    main()
