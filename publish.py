from __future__ import print_function

from datetime import timedelta
import dateutil.parser
import googleapiclient.discovery
from httplib2 import Http
from oauth2client import file, client, tools
import requests
import sys
import yaml

import logging
logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
GCAL_SCOPES = 'https://www.googleapis.com/auth/calendar'


class BamruClient(object):
    def __init__(self, prefix, session_id):
        self.session = requests.Session()
        # TODO: change this once the server supports oauth
        self.session.cookies['sessionid'] = session_id
        self.prefix = prefix

    def get(self, endpoint, *args, **kw):
        assert endpoint.startswith('/')
        return self.session.get(self.prefix + endpoint, *args, **kw)


class Publisher(object):
    def __init__(self, bamru_client, gcal_client):
        self.bamru_client = bamru_client
        self.gcal_client = gcal_client

    def gcal_event(self, bamru_event):
        start_dt = dateutil.parser.parse(bamru_event['start'])
        end_dt = None
        if bamru_event['finish']:
            end_dt = dateutil.parser.parse(bamru_event['finish'])
        if bamru_event['all_day']:
            start = {'date': start_dt.date().isoformat()}
            if end_dt:
                end = {'date': end_dt.date().isoformat()}
            else:
                end = {'date': start_dt.date().isoformat()}
        else:
            start = {'dateTime': start_dt.isoformat()}
            if end_dt:
                end = {'dateTime': end_dt.isoformat()}
            else:
                end = {'dateTime': (start_dt + timedelta(hours=1)).isoformat()}

        gcal_event = {
            'start': start,
            'end': end,
            'summary': bamru_event['title'],
        }
        if bamru_event['location']:
            gcal_event['location'] = bamru_event['location']

        description_lines = []
        if bamru_event['leaders']:
            description_lines.append("Leader(s): " + bamru_event['leaders'])
        if bamru_event['description']:
            description_lines.append(bamru_event['description'])
        if description_lines:
            gcal_event['description'] = '\n'.join(description_lines)

        return gcal_event


    def publish(self, calendar_id):
        logger.info("fetching events from bamru system")
        events = self.bamru_client.get('/events', params={'published': 'true'}).json()

        logger.info("clearing existing events")
        self.gcal_client.calendars().clear(calendarId=calendar_id).execute()

        logger.info("constructing batch request to create events")
        batch = self.gcal_client.new_batch_http_request()
        for event in events:
            batch.add(self.gcal_client.events().insert(calendarId=calendar_id,
                    body=self.gcal_event(event)))
        logger.info("executing batch request")
        batch.execute()

        logger.info("done")


def main(bamru_server, bamru_session_id, calendar_id, google_credentials_file, google_token_file):
    logging.basicConfig(format="[%(asctime)-15s %(levelname)s %(name)s] %(message)s")
    logger.setLevel(logging.INFO)

    store = file.Storage(google_token_file)
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets(google_credentials_file, GCAL_SCOPES)
        creds = tools.run_flow(flow, store)
    gcal_client = googleapiclient.discovery.build(
            'calendar', 'v3', http=creds.authorize(Http()))

    bamru_client = BamruClient(bamru_server, bamru_session_id)

    publisher = Publisher(bamru_client, gcal_client)
    publisher.publish(calendar_id)

if __name__ == "__main__":
    config_file = sys.argv.pop(1)
    with open(config_file) as f:
        config = yaml.safe_load(f)
    main(**config)
