import json
import os
import stat
import time
from sseclient import SSEClient as EventSource
from confluent_kafka import Producer
from nexusdata_collector.collector import Collector
from nexusdata_collector.common import CollectorId

company_name = 'Acme Data'
pipeline_name = 'Wiki Power Editors'
task_name = 'fetch'
topic_name = 'fetched'

# This simple program fetches data from a Wikipedia data feed, selects records from
# "power editors" (those with over 10k edits), and writes them to a Kafka topic.  

def create_credentials():
  # Create the username and password credentials for logging into the NexusData backend.  This
  # does not need to be done everytime, it was put here for illustration purposes and
  # so that this task can be quickly deployed to a new machine.  The credentials can also be 
  # passed in by environment variable, though that is less secure.
  credentials = open("./nexus-credentials", "w")
  credentials.write("nexus.username={}\n".format(os.environ['USER_EMAIL']))
  credentials.write("nexus.password={}\n".format(os.environ['USER_PASSWORD']))
  credentials.close()
  os.chmod("./nexus-credentials", stat.S_IRUSR)

def kafka_delivery_reporter(err, msg):
  if err is not None:
    print("Message delivery failed: {}".format(err))


def main():
  create_credentials()
  producer = Producer({'bootstrap.servers': os.environ['KAFKA_SERVER_ADDR']})
  # Start the collector.  The CollectorId tells NexusData which task this is monitoring
  collector_id = CollectorId(company_name, pipeline_name, task_name)
  collector = Collector(collector_id)
  for event in EventSource('https://stream.wikimedia.org/v2/stream/revision-create'):
    if event.event == 'message':
      try:
        data = json.loads(event.data)
        if 'performer' in data.keys() and 'user_edit_count' in data['performer'].keys() and \
            'user_is_bot' in data['performer'].keys() and \
            data['performer']['user_edit_count'] > 10000 and not data['performer']['user_is_bot'] \
            and int(data['rev_timestamp'][:4]) > 2019:
          msg = {
            "editor": data['performer']['user_text'],
            "editor_id": data['performer']['user_id'],
            "page": data['page_title'],
            "timestamp": data['rev_timestamp']
          }
          json_out = json.dumps(msg)
          # Pass the record to the NexusData collector.  It will collect the stats and at
          # configurable intervals forward the stats in the background to the backend.
          # This particular record is in JSON format.  The format is configurable.
          collector.collect_one(json_out)
          # Write the data to Kafka
          producer.poll(0)
          producer.produce(topic_name, json_out, callback=kafka_delivery_reporter)
      except ValueError:
        pass

  producer.flush()
  collector.close()


if __name__ == "__main__":
  main()
