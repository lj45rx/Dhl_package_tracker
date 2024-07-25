import requests
import time
import json
import os

# feld "events" abfragen

filename = "tracked_shipments.json"

"""
TODO
    using bad date format mm/dd/yyyy
        change to yyyy/mm/dd or yyyy-mm-dd
"""


class ShipmentDescriptor:
    # one shipment can have multiple events
    class EventDescriptor:
        def __init__(self, event_json):
            self.raw_json = event_json
            self.parse_event_json()

        def parse_event_json(self):
            # expected keys = ['timestamp', 'location', 'statusCode', 'status', 'description']

            self.timestamp = self.raw_json["timestamp"]
            self.status_code = self.raw_json["statusCode"]
            self.status = self.raw_json["status"]
            self.status_desc = self.raw_json["description"]

            # "status" and "description" might be same string
            if self.status == self.status_desc:
                self.status_desc = ""

        def get_nice_string(self):
            result_string = ""
            result_string += f"    [{get_time_string_from_timestamp(self.timestamp)}] ({self.status_code})\n"

            res_lines = split_line_if_too_long(self.status,
                                         76, 72)  # split so that, first line max 76, following max 72 chars
            if res_lines[0] != "":
                result_string += f"\t{res_lines[0]}"

            for line in res_lines[1:]:
                result_string += f"\n\t\t{line}"

            return result_string

        def __str__(self):
            desc = ""
            if self.status_desc != "":
                desc = f" - {self.status_desc}"
            return f"{self.timestamp}: ({self.status_code}) {self.status}{desc}"

        def __eq__(self, other):
            # assume same if status-text and timestamp are equal
            return self.timestamp == other.timestamp and self.status == other.status

        def __lt__(self, other):
            # order by timestamp
            return self.timestamp < other.timestamp

    def __init__(self, in_json):
        self.full_json = in_json  # as saved in file
        self.response_json = None  # as received as response

        self.name = ""
        self.tracking_number = ""
        self.added = ""
        self.last_query = ""
        self.last_update = ""

        self.events: [ShipmentDescriptor.EventDescriptor] = []

        self.was_updated = False
        self.new_events = []

        self.parse_json()

    def parse_json(self):
        # check expected keys exist
        keys_ok = True
        expected_keys = ['added', 'last_query', 'last_update', 'name', 'status_raw', 'trackingNumber']
        for key in self.full_json.keys():
            if key not in expected_keys:
                keys_ok = False
                break

        if not keys_ok:
            print("Error: json object did not contain expected keys")
            print("expected:", expected_keys)
            print("found:   ", self.full_json.keys())
            exit(0)

        self.name = self.full_json["name"]
        self.tracking_number = self.full_json["trackingNumber"]
        self.added = self.full_json["added"]
        self.last_query = self.full_json["last_query"]
        self.last_update = self.full_json["last_update"]
        self.response_json = self.load_as_json(self.full_json["status_raw"])

        shipment_id, events = self.parse_response_json(self.response_json)

        self.assert_is_correct_tracking_number(shipment_id)

        self.events = events

    def assert_is_correct_tracking_number(self, tracking_number):
        if tracking_number.lower() != self.tracking_number.lower():
            print(f"Error: trackingNumbers do not match {tracking_number} {self.tracking_number}")
            exit(1)

    def load_as_json(self, obj):
        if type(obj) == str:
            obj = json.loads(obj)
        return obj

    def parse_response_json(self, _json: str or json):  # TODO just guessing - no error but actually correct??
        _json = self.load_as_json(_json)

        # only want part of the api-response - extract if full response was given
        if "shipments" in _json.keys():
            # only want single shipment
            if len(_json["shipments"]) != 1:
                print("ERROR len(response[\"shipments\"]) was not 1 - exiting")
                exit(1)

            _json = _json["shipments"][0]

        # expect keys = ['serviceUrl', 'id', 'service', 'origin', 'status', 'details', 'events']
        # id: tracking number
        shipment_id = _json["id"]

        # status: newest event
        status = _json["status"]
        # events: list of all events
        events = _json["events"]

        # expecting status to be included in events
        if status not in events:
            events.append(status)

        event_descs = []
        for event in events:
            event_descs.append(ShipmentDescriptor.EventDescriptor(event))

        event_descs.sort(reverse=True)

        return [shipment_id, event_descs]

    def status_has_changed(self, _json):
        shipment_id, reply_events = self.parse_response_json(_json)

        self.assert_is_correct_tracking_number(shipment_id)

        #for event in self.events:
        #    print(event)

        new_events = []
        for event in reply_events:
            #print(event)
            if event not in self.events:
                new_events.append(event)

        self.was_updated = len(new_events) > 0
        self.new_events = new_events

        # update self.full_json for correct saving
        self.last_query = self.full_json["last_query"] = get_time_string()
        if self.was_updated:
            self.events = reply_events
            self.last_update = self.full_json["last_update"] = \
                get_time_string_from_timestamp(reply_events[0].timestamp)
            self.response_json = self.full_json["status_raw"] = _json

        return [len(new_events) > 0, new_events]

    def get_status_string(self):
        result_string = ""
        for i, event in enumerate(self.events):
            if i > 0:
                result_string += "\n"

            result_string += event.get_nice_string()

        return result_string


# handle file, do api calls, stand between shipment-objects and ui
class DhlShipmentChecker:
    def __init__(self, api_key, dummy_calls=False):
        # self.json_obj = None  # full json-object as saved in file
        self.dummy_calls = dummy_calls
        self.api_key = api_key
        self.shipments = []  # containing only parts of individual shipments, some convenience functions
        self.status_changed = None

        self.saved_json = None
        self.load_json_file()

        for shipment in self.json_obj:
            self.shipments.append(ShipmentDescriptor(shipment))

    def get_num_tracked_shipments(self):
        return len(self.shipments)

    def update_shipment_status_by_index(self, index):
        return self.update_shipment_status(self.json_obj[index])

    def update_shipment_status(self, shipment: ShipmentDescriptor):
        if self.dummy_calls:
            # pretend as if success but no changes, don't update "last query"
            return [200, "dummy run", False, [shipment.events[0]]]  # newest event

        tracking_number = shipment.tracking_number
        query_result = self.do_shipment_status_api_call(tracking_number)
        if not query_result.status_code == 200:
            return [query_result.status_code, query_result.reason, False, [shipment.events[0]]]

        # for successful call
        #  give response to shipment-object - ask if it has changed
        status_has_changed, new_events = shipment.status_has_changed(query_result.text)
        self.overwrite_json_file()

        if status_has_changed:
            return [query_result.status_code, query_result.reason, True, new_events]
        else:
            return [query_result.status_code, query_result.reason, False, [shipment.events[0]]]  # newest event

    def add_tracked_shipment(self, tracking_number, optional_name=""):
        new_shipment_dict = dict()
        new_shipment_dict["trackingNumber"] = tracking_number
        new_shipment_dict["added"] = get_time_string()
        new_shipment_dict["last_query"] = get_time_string()
        new_shipment_dict["last_update"] = get_time_string()
        new_shipment_dict["name"] = optional_name

        query_result = self.do_shipment_status_api_call(tracking_number)

        if not query_result.status_code == 200:
            print(f"error with request: {query_result.status_code} \"{query_result.reason}\"")
            return [query_result.status_code, query_result.reason, None]

        new_shipment_dict["status_raw"] = query_result.text

        self.shipments.append(ShipmentDescriptor(new_shipment_dict))
        self.overwrite_json_file()

        return [query_result.status_code, query_result.reason, self.shipments[-1]]

    def delete_tracked_shipment(self, shipment: ShipmentDescriptor, overwrite_file=True):
        self.shipments.remove(shipment)

        # CAUTION: file might be overwritten without "temporarily removed" shipment after updates etc
        if overwrite_file:
            self.overwrite_json_file()

    def do_shipment_status_api_call(self, tracking_number):
        # ex
        # curl -X GET 'https://api-eu.dhl.com/track/shipments?trackingNumber=7777777770' -H 'DHL-API-Key:PasteHere_ConsumerKey
        response = requests.get(f"https://api-eu.dhl.com/track/shipments?trackingNumber={tracking_number}",
                                headers={
                                    "DHL-API-Key": self.api_key
                                }
                                )
        return response

    def load_json_file(self):
        if os.path.isfile(filename):
            with open(filename, 'r') as openfile:
                self.json_obj = json.load(openfile)
            self.status_changed = [None] * len(self.json_obj)
        else:
            with open(filename, 'w') as fp:
                fp.write("[]")
            self.json_obj = []
            self.status_changed = []

    def overwrite_json_file(self):
        # write to tmp file first, then replace original file
        # TODO does this make sense?

        full_json = []
        for shipment in self.shipments:
            full_json.append(shipment.full_json)

        tmp_filename = f"tmp_{time.time()}.json"
        with open(tmp_filename, "w") as outfile:
            json.dump(full_json, outfile, indent=4, sort_keys=True)

        os.replace(tmp_filename, filename)


# ==============================================================================

def get_time_string(time_obj = None):
    if time_obj is None:
        time_obj = time.localtime()
    time_string = time.strftime("%m/%d/%Y, %H:%M:%S", time_obj)
    return time_string

def get_time_string_from_timestamp(inp_str):
    # eg "2023-04-06T15:38:00"
    time_obj = time.strptime(inp_str, '%Y-%m-%dT%H:%M:%S')
    return get_time_string(time_obj)

def split_line_if_too_long(string, max_line_length, second_max_line_length=None):
    if len(string) <= max_line_length:
        return [string]

    change_line_length = second_max_line_length is not None

    result = []
    split = string.split()

    temp = split[0]
    for word in split[1:]:
        if (len(temp) + 1 + len(word)) > max_line_length:
            result.append(temp)
            temp = word

            if change_line_length:
                change_line_length = False
                max_line_length = second_max_line_length
        else:
            temp += " " + word

    result.append(temp)

    return result


file_string = r"""
[
    {
        "added": "05/08/2023, 21:30:30",
        "last_query": "08/03/2023, 13:45:29",
        "last_update": "06/07/2023, 14:26:00",
        "name": "atsu jp",
        "status_raw": "{\"shipments\":[{\"serviceUrl\":\"https://www.dhl.de/de/privatkunden.html?piececode=CN054067116JP&cid=c_dhl_de_352_20205002_151_M040\",\"id\":\"CN054067116JP\",\"service\":\"parcel-de\",\"origin\":{\"address\":{\"countryCode\":\"JP\"}},\"destination\":{\"address\":{\"countryCode\":\"DE\"}},\"status\":{\"timestamp\":\"2023-06-07T14:26:00\",\"location\":{\"address\":{\"addressLocality\":\"Germany\"}},\"statusCode\":\"delivered\",\"status\":\"Delivery successful.\",\"description\":\"Delivery successful.\"},\"details\":{\"product\":{\"productName\":\"DHL PAKET (parcel)\"},\"proofOfDeliverySignedAvailable\":false,\"totalNumberOfPieces\":1,\"pieceIds\":[\"CN054067116JP\"]},\"events\":[{\"timestamp\":\"2023-06-07T14:26:00\",\"location\":{\"address\":{\"addressLocality\":\"Germany\"}},\"statusCode\":\"delivered\",\"status\":\"Delivery successful.\",\"description\":\"Delivery successful.\"},{\"timestamp\":\"2023-06-07T08:40:00\",\"statusCode\":\"transit\",\"status\":\"Being delivered.\",\"description\":\"Being delivered.\"},{\"timestamp\":\"2023-06-07T04:44:00\",\"location\":{\"address\":{\"addressLocality\":\"Germany\"}},\"statusCode\":\"transit\",\"status\":\"Shipment arrived in the recipient's region\",\"description\":\"Shipment arrived in the recipient's region\"},{\"timestamp\":\"2023-06-06T10:20:00\",\"location\":{\"address\":{\"addressLocality\":\"Germany\"}},\"statusCode\":\"transit\",\"status\":\"Parcel center of origin.\",\"description\":\"Parcel center of origin.\"},{\"timestamp\":\"2023-06-06T10:19:00\",\"location\":{\"address\":{\"addressLocality\":\"Germany\"}},\"statusCode\":\"transit\",\"status\":\"Customs clearance process completed\",\"description\":\"Customs clearance process completed\"},{\"timestamp\":\"2023-06-05T10:13:00\",\"location\":{\"address\":{\"addressLocality\":\"Germany\"}},\"statusCode\":\"transit\",\"status\":\"Customs clearance in progress\",\"description\":\"Customs clearance in progress\"},{\"timestamp\":\"2023-06-02T16:59:00\",\"location\":{\"address\":{\"addressLocality\":\"Germany\"}},\"statusCode\":\"transit\",\"status\":\"Customs clearance in progress\",\"description\":\"Customs clearance in progress\"},{\"timestamp\":\"2023-06-02T16:56:00\",\"location\":{\"address\":{\"addressLocality\":\"Germany\"}},\"statusCode\":\"transit\",\"status\":\"Customs clearance process started\",\"description\":\"Customs clearance process started\"},{\"timestamp\":\"2023-06-02T16:55:00\",\"location\":{\"address\":{\"addressLocality\":\"Germany\"}},\"statusCode\":\"transit\",\"status\":\"Arrival in the destination country/destination area.\",\"description\":\"Arrival in the destination country/destination area.\"}]}],\"possibleAdditionalShipmentsUrl\":[\"/track/shipments?trackingNumber=CN054067116JP&service=freight\",\"/track/shipments?trackingNumber=CN054067116JP&service=dgf\",\"/track/shipments?trackingNumber=CN054067116JP&service=ecommerce\",\"/track/shipments?trackingNumber=CN054067116JP&service=parcel-nl\",\"/track/shipments?trackingNumber=CN054067116JP&service=parcel-pl\",\"/track/shipments?trackingNumber=CN054067116JP&service=express\",\"/track/shipments?trackingNumber=CN054067116JP&service=post-de\",\"/track/shipments?trackingNumber=CN054067116JP&service=sameday\",\"/track/shipments?trackingNumber=CN054067116JP&service=parcel-uk\",\"/track/shipments?trackingNumber=CN054067116JP&service=ecommerce-apac\",\"/track/shipments?trackingNumber=CN054067116JP&service=ecommerce-europe\",\"/track/shipments?trackingNumber=CN054067116JP&service=svb\",\"/track/shipments?trackingNumber=CN054067116JP&service=post-international\"]}",
        "trackingNumber": "cn054067116jp"
    }
]
"""
if __name__ == '__main__':
    res_string = "{\"shipments\":[{\"serviceUrl\":\"https://www.dhl.de/de/privatkunden.html?piececode=CN054067116JP&cid=c_dhl_de_352_20205002_151_M040\",\"id\":\"CN054067116JP\",\"service\":\"parcel-de\",\"origin\":{\"address\":{\"countryCode\":\"JP\"}},\"status\":{\"timestamp\":\"2023-04-06T15:38:00\",\"location\":{\"address\":{\"addressLocality\":\"Japan\"}},\"statusCode\":\"transit\",\"status\":\"The shipment will be transported to the destination country/destination area and, from there, handed over to the delivery organization.\",\"description\":\"The shipment will be transported to the destination country/destination area and, from there, handed over to the delivery organization.\"},\"details\":{\"proofOfDeliverySignedAvailable\":false,\"totalNumberOfPieces\":1,\"pieceIds\":[\"CN054067116JP\"]},\"events\":[{\"timestamp\":\"2023-04-06T15:38:00\",\"location\":{\"address\":{\"addressLocality\":\"Japan\"}},\"statusCode\":\"transit\",\"status\":\"The shipment will be transported to the destination country/destination area and, from there, handed over to the delivery organization.\",\"description\":\"The shipment will be transported to the destination country/destination area and, from there, handed over to the delivery organization.\"},{\"timestamp\":\"2023-04-06T11:07:00\",\"location\":{\"address\":{\"addressLocality\":\"Japan\"}},\"statusCode\":\"transit\",\"status\":\"The shipment has arrived at the export parcel center\",\"description\":\"The shipment has arrived at the export parcel center\"},{\"timestamp\":\"2023-04-05T11:17:00\",\"location\":{\"address\":{\"addressLocality\":\"Japan\"}},\"statusCode\":\"transit\",\"status\":\"The shipment has arrived at the parcel center of origin\",\"description\":\"The shipment has arrived at the parcel center of origin\"}]}],\"possibleAdditionalShipmentsUrl\":[\"/track/shipments?trackingNumber=CN054067116JP&service=freight\",\"/track/shipments?trackingNumber=CN054067116JP&service=dgf\",\"/track/shipments?trackingNumber=CN054067116JP&service=ecommerce\",\"/track/shipments?trackingNumber=CN054067116JP&service=parcel-nl\",\"/track/shipments?trackingNumber=CN054067116JP&service=parcel-pl\",\"/track/shipments?trackingNumber=CN054067116JP&service=express\",\"/track/shipments?trackingNumber=CN054067116JP&service=post-de\",\"/track/shipments?trackingNumber=CN054067116JP&service=sameday\",\"/track/shipments?trackingNumber=CN054067116JP&service=parcel-uk\",\"/track/shipments?trackingNumber=CN054067116JP&service=ecommerce-apac\",\"/track/shipments?trackingNumber=CN054067116JP&service=ecommerce-europe\",\"/track/shipments?trackingNumber=CN054067116JP&service=svb\",\"/track/shipments?trackingNumber=CN054067116JP&service=post-international\"]}"

    json_obj = json.loads(file_string)
    shipment0_json = json_obj[0]

    desc = ShipmentDescriptor(shipment0_json)

    print("added\n\t", desc.added)
    print("name\n\t", desc.name)
    print("number\n\t", desc.tracking_number)
    print("last update\n\t", desc.last_update)
    print("last query\n\t", desc.last_query)
    print("Events:")
    for event in desc.events:
        print("\t", event)
