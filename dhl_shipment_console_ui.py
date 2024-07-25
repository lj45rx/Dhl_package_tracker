import colorama
from colorama import Fore, Back, Style

from dhl_shipment_status_checker import DhlShipmentChecker

"""
TODO
bad handling of inputs
eg make function for "(y/n):" checks
"""
class DhlShipmentConsoleUi:
    def __init__(self, api_key, dummy_calls=False):
        colorama.init()
        self.no_shipments = 0
        self.status_checker = DhlShipmentChecker(api_key, dummy_calls)

    def __del__(self):
        colorama.deinit()

    def start(self):
        shipments = self.status_checker.shipments
        self.no_shipments = self.status_checker.get_num_tracked_shipments()
        print(Back.WHITE + Fore.BLACK, end="")
        print(f"currently tracking {self.no_shipments} shipment(s)")
        print(Style.RESET_ALL, end="")

        if self.no_shipments == 0:
            return self.ask_for_further_actions()

        some_changes = False
        changes = []

        for i, shipment in enumerate(shipments):
            if shipment.name != "":
                name = f"({shipment.name}) "
            else:
                name = ""

            print(f"... querying shipment {Fore.YELLOW}\"{shipment.tracking_number}\" {name}{Style.RESET_ALL}({i+1}/{self.no_shipments})\t", end="", flush=True)
            res = self.status_checker.update_shipment_status(shipment)

            success = res[0] == 200
            some_changes = res[2]

            if success:
                print(Back.GREEN, end="")
            else:
                print(Back.RED, end="")  # red background

            print(f"[{res[0]} - {res[1]}]" + Style.RESET_ALL)

            if success and some_changes:
                some_changes = True

                print(Back.BLUE, "New Status:", Style.RESET_ALL)
                for status in res[3]:
                    print(status.get_nice_string())
            else:
                print(Back.WHITE + Fore.BLACK, "Newest known status:", Style.RESET_ALL)
                print(res[3][0].get_nice_string())

        print("\n" + Back.WHITE + Fore.BLACK, "----- finished -----", Style.RESET_ALL)

        # TODO reacto to errors?
        if not some_changes:
            print(Fore.CYAN + ">>> no updates in status")

        print(Style.RESET_ALL, end="")  # reset background

        return self.ask_for_further_actions()

    def print_spacing(self):
        print("-" * 40)

    def ask_for_further_actions(self):
        self.print_spacing()
        print("[1] print detailed statuses")
        print("[2] track new shipment")
        if self.no_shipments > 0:
            print("[3] stop tracking a shipment")
        print("[q/Enter] quit")

        inp_str = input(">> ")

        if inp_str == "1":
            self.print_detailed_statuses()
        elif inp_str == "2":
            self.add_new_shipment_dialog()
        elif inp_str == "3":
            self.select_shipment_to_stop_tracking_dialog()
        elif inp_str in ["q", ""]:
            print("exiting")
            exit(0)
        else:
            self.ask_for_further_actions()

    def print_detailed_statuses(self):
        shipments = self.status_checker.shipments
        no_shipments = len(shipments)
        if no_shipments == 0:
            print("nothing to show")
            return self.ask_for_further_actions()

        for i, shipment in enumerate(shipments):
            if shipment.name == "":
                name = f"{shipment.tracking_number}"
            else:
                name = f"{shipment.name} ({shipment.tracking_number})"

            print(f"({i+1}/{no_shipments}) {name}")
            print(shipment.get_status_string())

        inp = input("\nPress Enter to continue...")
        return self.ask_for_further_actions()

    def add_new_shipment_dialog(self):
        self.print_spacing()
        tracking_number = input("Tracking Number: ")
        name = input("Name (optional): ")

        print(tracking_number, name)

        for i in range(3):
            conf_inp = input(f"add shipment \"{tracking_number}\" \"{name}\"? (y/n): ")

            if conf_inp in ["n", "N"]:
                print("aborting")
                self.ask_for_further_actions()
            elif conf_inp in ["y", "Y", "j", "J"]:
                return self.try_adding_new_shipment(tracking_number, name)
            else:
                print("unknown input")
        self.ask_for_further_actions()

    def select_shipment_to_stop_tracking_dialog(self):
        self.print_spacing()
        print("Select shipment to stop tracking:")
        shipments = self.status_checker.shipments
        no_shipments = len(shipments)

        idx = -1
        if no_shipments == 0:  # this should never happen, but handle just in case
            print("  no shipments tracked")
            idx = -1
        elif no_shipments == 11:
            idx = 0
        elif no_shipments > 0:
            for i, shipment in enumerate(shipments):
                print(f"[{i+1}] {shipment.tracking_number} {shipment.name}")

            inp_str = input(">> ")

            try:
                inp_idx = int(inp_str)
            except:
                inp_idx = -1

            # -1 if cast to int failed, must be in [1, no_shipments]
            if inp_idx == -1 or inp_idx > no_shipments or inp_idx < 1:
                idx = -1
                print("unknown input")
            else:
                idx = inp_idx-1

        if idx == -1:
            # "abort"
            pass
        else:
            shipment = shipments[idx]
            conf_inp = input(f"stop tracking {shipment.tracking_number} {shipment.name}? (y/n): ")

            if conf_inp in ["y", "Y", "j", "J"]:
                self.status_checker.delete_tracked_shipment(shipment)
                print(f"deleting {shipment.tracking_number} {shipment.name}")
            else:
                if conf_inp in ["n", "N"]:
                    print("aborting")
                else:
                    print("unknown input")
        self.ask_for_further_actions()

    def try_adding_new_shipment(self, tracking_number, name):
        self.print_spacing()
        if name != "":
            print_name = f"({name}) "
        else:
            print_name = ""
        print(f"querying shipment \"{tracking_number}\" {name}\t", end="", flush=True)

        res = self.status_checker.add_tracked_shipment(tracking_number, name)

        print(f"[{res[0]} - {res[1]}]")

        if res[2] is not None:
            print("")
            print(res[2].get_status_string())
        else:
            print("failed to query shipment - aborting")

        inp = input("\nPress Enter to continue...")
        return self.ask_for_further_actions()


if __name__ == '__main__':
    api_key = -7
    ui = DhlShipmentConsoleUi(api_key, dummy_calls=True)
    ui.start()
