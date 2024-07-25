'''
DHL "Shipment Tracking - Unified" API
https://developer.dhl.com/api-reference/shipment-tracking#get-started-section/
'''

import sys

from dhl_shipment_console_ui import DhlShipmentConsoleUi

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("ERROR: api-key must be passed as parameter to this script")
        exit(1)

    api_key = sys.argv[1]

    ui = DhlShipmentConsoleUi(api_key)
    ui.start()
