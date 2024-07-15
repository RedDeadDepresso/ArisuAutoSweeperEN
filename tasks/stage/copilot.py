import re

from module.base.timer import Timer
from module.exception import RequestHumanTakeover
from module.logger import logger
from module.ui.switch import Switch
from module.ocr.ocr import Digit
from tasks.base.ui import UI
from tasks.base.assets.assets_base_page import MISSION_CHECK
from tasks.stage.assets.assets_stage_copilot import *
from tasks.stage.stage import StageState, Stage

PRESETS = [PRESET1_ON, PRESET2_ON, PRESET3_ON, PRESET4_ON]

SWITCH_UNIT1 = Switch('Unit1_Switch')
SWITCH_UNIT1.add_state('on', UNIT1_ON)
SWITCH_UNIT1.add_state('off', UNIT1_OFF)

SWITCH_UNIT2 = Switch('Unit2_Switch')
SWITCH_UNIT2.add_state('on', UNIT2_ON)
SWITCH_UNIT2.add_state('off', UNIT2_OFF)

SWITCH_UNIT3 = Switch('Unit3_Switch')
SWITCH_UNIT3.add_state('on', UNIT3_ON)
SWITCH_UNIT3.add_state('off', UNIT3_OFF)

SWITCH_UNIT4 = Switch('Unit4_Switch')
SWITCH_UNIT4.add_state('on', UNIT4_ON)
SWITCH_UNIT4.add_state('off', UNIT4_OFF)

UNIT_SWITCHES = [SWITCH_UNIT1, SWITCH_UNIT2, SWITCH_UNIT3, SWITCH_UNIT4]

SWITCH_AUTO_END = Switch('Auto_End_Switch')
SWITCH_AUTO_END.add_state('on', AUTO_END_ON)
SWITCH_AUTO_END.add_state('off', AUTO_END_OFF)

SWITCH_SKIP_BATTLE = Switch('Skip_Battle_Switch')
SWITCH_SKIP_BATTLE.add_state('on', SKIP_BATTLE_ON)
SWITCH_SKIP_BATTLE.add_state('off', SKIP_BATTLE_OFF)

class Copilot(UI):
    """A class dedicated to automate fights"""
    def __init__(self, config, device):
        super().__init__(config, device) 
        self.ocr_unit = Digit(OCR_UNIT)

    """---------------------- UTILITY METHODS ------------------------"""
    def get_default_type_to_preset(self) -> dict[str, list[int, int]]:
        """
        Validate preset settings and returs a dictionary
        mapping each type to its preset e.g {burst1: [1, 1]}
        """
        formation_config = self.config.cross_get("Settings.Formation")
        type_to_preset: dict[str, str] =  {
            "burst1": formation_config["burst1"],
            "burst2": formation_config["burst2"],
            "pierce1": formation_config["pierce1"],
            "pierce2": formation_config["pierce2"],
            "mystic1": formation_config["mystic1"],
            "mystic2": formation_config["mystic2"]
        }
        valid = True
        for type, preset in type_to_preset.items():
            preset_list = []
            if isinstance(preset, str):
                preset = re.sub(r'[ \t\r\n]', '', preset)
                preset = preset.split("-")
                if len(preset) == 2:
                    column = preset[0]
                    row = preset[1]
                    if (column.isdigit() and 1 <= int(column) <= 4) and (row.isdigit() and 1 <= int(row) <= 5):
                        preset_list = [int(num) for num in preset]
            if not preset_list:
                logger.error(f"Failed to read {type}'s preset settings")
                valid = False
                continue
            type_to_preset[type] = preset_list
        if not valid:
            raise RequestHumanTakeover
        return type_to_preset
    
    def sleep(self, num: int):
        timer = Timer(num).start()
        while not timer.reached():
            pass

    def click(self, x, y, interval=1):
        self.device.click_methods.get(self.config.Emulator_ControlMethod, self.device.click_adb)(x, y)
        if interval:
            # sleep because clicks can be too fast when executing actions
            self.sleep(interval)

    def click_then_check(self, coords: tuple[int, int], dest_check: ButtonWrapper):
        while 1:
            self.device.screenshot()
            if self.appear(dest_check):
                return True
            self.click(*coords, interval=2)

    def select_then_check(self, dest_enter: ButtonWrapper, dest_check: ButtonWrapper):
        while 1:
            self.device.screenshot()
            self.appear_then_click(dest_enter, interval=1)
            if self.appear(dest_check):
                return True
            self.sleep(2)
            
    def set_switch(self, switch: Switch):
        """
        Set skip switch to on
        Returns:
            True if switch is set, False if switch not found
        """
        while 1:
            self.device.screenshot()
            if not switch.appear(main=self):
                logger.info(f'{switch.name} not found')
                continue
            switch.set('on', main=self)
            return True

    """---------------------- FORMATION METHODS ------------------------"""
    def choose_from_preset(self, type: str, type_to_preset: dict):
        preset, row = type_to_preset[type]
        preset_index = preset - 1
        self.select_then_check(LAYOUT, PRESET_LIST)
        PRESET = PRESETS[preset_index]
        while not self.match_color(PRESET, threshold=50):
            self.device.screenshot()
            self.click_with_interval(PRESET, interval=1)

        click_first = lambda : self.click_then_check((1145, 320), MOBILIZE)
        click_second = lambda : self.click_then_check((1145, 530), MOBILIZE)
        swipe = lambda : self.device.swipe((500, 625), (500, 350))
        wait = lambda : self.wait_until_stable(
                PRESET_WINDOW,
                timer=Timer(3, 0),
                timeout=Timer(1.5, 5)
            )
        match row:
            case 1:
                click_first()
            case 2:
                click_second()
            case 3:
                swipe()
                wait()
                click_first()
            case 4:
                swipe()
                wait()
                click_second()
            case 5: 
                swipe()
                swipe()
                wait()
                click_second()

    def choose_unit(self, unit: int):
        unit_index = unit - 1 
        unit_switch = UNIT_SWITCHES[unit_index]
        self.set_switch(unit_switch)

    def goto_formation_page(self, start_coords: tuple[int, int]):
        self.click_then_check(start_coords, MOBILIZE)

    def formation(self, stage: Stage, type_to_preset: dict):
        if stage.state == StageState.SUB:
            # Select a unit to start the battle 
            self.choose_unit(1)
            if type_to_preset:
                type = stage.formation_info
                self.choose_from_preset(type, type_to_preset)
            self.click_with_interval(MOBILIZE, interval=1)
        else:
            unit = 1
            for type, start_coords in stage.formation_start_info:
                self.goto_formation_page(start_coords)
                self.choose_unit(unit)
                if type_to_preset:
                    self.choose_from_preset(type, type_to_preset)
                self.select_then_check(MOBILIZE, MISSION_INFO)
                unit += 1

    """---------------------- FIGHT METHODS ------------------------"""
    def begin_mission(self):
        # start the fight after formation. Not needed for SUB mission.
        self.select_then_check(BEGIN_MISSION, END_PHASE)

    def check_skip_auto_over(self):
        # set skip battle and auto end when entering the map
        self.set_switch(SWITCH_SKIP_BATTLE)
        self.set_switch(SWITCH_AUTO_END)

    def get_force(self) -> int:
        # detect the current active unit in the map
        self.device.screenshot()
        current_unit = self.ocr_unit.ocr_single_line(self.device.image)
        if current_unit == 0:
            return self.get_force()
        return current_unit
    
    def wait_formation_change(self, force_index: int) -> int:
        logger.info("Wait formation change")
        origin = force_index
        while force_index == origin:
            force_index = self.get_force()
            self.sleep(1)
        return force_index
    
    def handle_all_mission_popup(self):
        self.sleep(2)
        while not self.match_color(MISSION_INFO):
            self.device.screenshot()
            if self.match_color(MISSION_INFO):
                break
            if self.appear_then_click(MISSION_INFO_POPUP):
                continue
            if self.appear_then_click(MOVE_UNIT):
                continue
            if self.appear_then_click(RECEIVED_CHEST):
                continue

    def handle_mission_popup(self, button: ButtonWrapper, skip_first_screenshot=True):
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()
            if self.match_color(MISSION_INFO):
                break
            if self.appear_then_click(button, interval=2):
                continue

    def confirm_teleport(self):
        # Detect and confirm the end of the phase
        while 1: 
            self.device.screenshot()
            if self.appear(MOVE_UNIT):
                self.handle_mission_popup(MOVE_UNIT)
                break

    def end_turn(self):
        # Detect and confirm the end of the phase
        while 1:
            self.device.screenshot()
            if not self.match_color(END_PHASE):
                self.handle_all_mission_popup()
                break
            self.appear_then_click(END_PHASE)
            self.sleep(2)

    def wait_over(self):
        #self.sleep(2)
        self.select_then_check(MISSION_INFO, MISSION_INFO_POPUP)
        self.handle_mission_popup(MISSION_INFO_POPUP)

    def start_action(self, actions, manual_boss: bool):
        for i, act in enumerate(actions):
            if manual_boss and i == len(actions) - 1:
                logger.warning("Actions completed. Waiting for manual boss...")
                return
            desc = "start " + str(i + 1) + " operation : "
            if 'desc' in act:
                desc += act['desc']
            logger.info(desc)
            force_index = self.get_force()
            op = act['t']
            if type(op) is str:
                op = [op]
            if 'p' in act:
                if type(act['p']) is tuple:
                    act['p'] = [act['p']]
            for j in range(0, len(op)):
                self.sleep(1)
                if op[j] == 'click':
                    self.click(act['p'][0][0], act['p'][0][1])
                    act['p'].pop(0)
                elif op[j] == 'teleport':
                    self.confirm_teleport()
                elif op[j] == 'exchange':
                    self.click(83, 557)
                    force_index = self.wait_formation_change(force_index)
                elif op[j] == 'exchange_twice':
                    self.click(83, 557)
                    force_index = self.wait_formation_change(force_index)
                    self.click(83, 557)
                    force_index = self.wait_formation_change(force_index)
                elif op[j] == 'end-turn':
                    self.end_turn()
                    if i != len(actions) - 1:
                        self.wait_over()
                elif op[j] == 'click_and_teleport':
                    self.click(act['p'][0][0], act['p'][0][1])
                    act['p'].pop(0)
                    self.confirm_teleport()
                elif op[j] == 'choose_and_change':
                    self.click(act['p'][0][0], act['p'][0][1])
                    self.click(act['p'][0][0] - 100, act['p'][0][1])
                    act['p'].pop(0)
                elif op[j] == 'exchange_and_click':
                    self.click(83, 557)
                    force_index = self.wait_formation_change(force_index)
                    #self.sleep(0.5)
                    self.sleep(1)
                    self.click(act['p'][0][0], act['p'][0][1])
                    act['p'].pop(0)
                elif op[j] == 'exchange_twice_and_click':
                    self.click(83, 557)
                    force_index = self.wait_formation_change(force_index)
                    self.click(83, 557)
                    force_index = self.wait_formation_change(force_index)
                    #self.sleep(0.5)
                    self.sleep(1)
                    self.click(act['p'][0], act['p'][1])
                    act['p'].pop(0)

            if 'ec' in act:
                self.wait_formation_change(force_index)
            if 'wait-over' in act:
                self.wait_over()
                self.sleep(2)
            if i != len(actions) - 1:
                self.handle_all_mission_popup()

        logger.warning("Actions completed, waiting to enter the battle...")

    def auto_accelerate(self):
        # click on the accelerate and auto button during the fight
        while 1:
            self.device.screenshot()
            self.device.click_record_clear()
            self.device.stuck_record_clear()
            if self.appear(BATTLE_COMPLETE):
                break
            elif not self.match_color(AUTO, threshold=50):
                self.device.click(AUTO)
            elif not self.match_color(ACCELERATE, threshold=50):
                self.device.click(ACCELERATE)
            elif self.match_color(AUTO, threshold=50) and self.match_color(ACCELERATE, threshold=50):
                break
            self.sleep(1)

    def auto_fight(self):
        # Wait for the game stage to finish loading
        self.handle_loading()
        # Change the settings for automatic fighting
        self.auto_accelerate()
        # Log a warning message indicating that the check for automatic skill release is completed
        logger.warning("Check for automatic skill release completed")

    def goto_parent_page(self):
        # go back to mission page after fight
        while 1:
            self.device.screenshot()
            if self.appear(MISSION_CHECK):
                break
            if self.appear_then_click(BATTLE_COMPLETE, interval=1):
                continue
            if self.appear_then_click(RANK, interval=1):
                continue
            if self.appear_then_click(MISSION_COMPLETE, interval=1):
                continue
            if self.appear_then_click(REWARD_ACQUIRED, interval=1):
                continue
            self.device.click_record_clear()
            self.device.stuck_record_clear()

    def fight(self, stage: Stage, manual_boss: bool):
        if stage.state != StageState.SUB:
            # Click to start the task
            self.begin_mission()
            # Check for skip auto over
            self.check_skip_auto_over()
            # Start moving through the grid
            self.start_action(stage.action_info, manual_boss)
            # Auto battle
        if not manual_boss or stage.state == StageState.SUB:
            self.auto_fight()
        self.goto_parent_page()
            
