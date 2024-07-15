from tasks.mission.ui import MissionUI
from tasks.stage.ap import AP
from tasks.stage.stage import Stage
from tasks.auto_mission.ui import AutoMissionUI
from enum import Enum

from module.base.timer import Timer
from module.exception import RequestHumanTakeover
from module.logger import logger

import re

class AutoMissionStatus(Enum):
    AP = 0 # Calculate AP and decide to terminate Auto-Mission module or not
    STAGES_DATA = 1 # Retrieve stages data for the area and resolve conflicts for type_to_preset
    NAVIGATE = 2 # Navigate to the area and select mode
    ENTER = 3 # Enter the first stage in the stage list
    CHECK = 4 # Check stages and find a stage that requires to be completed
    START = 5 # Start the stage
    FORMATION = 6 # Select units based on the types required by the stage
    FIGHT = 7 # Fight the stage
    END = 8 # Update task
    FINISH = -1 # Indicate termination of Auto-Mission module

class AutoMission(AP, MissionUI, AutoMissionUI):
    def __init__(self, config, device):
        super().__init__(config, device) 
        self.task: list[str, list[int], bool] = None
        self.previous_mode: str = None
        self.previous_area: int = None
        self.current_stage: Stage = None
        self.stages_data: dict = None
        self.default_type_to_preset: dict = self.get_default_type_to_preset()
        self.current_type_to_preset: dict = None

    def validate_area(self, mode, area_input) -> list[int]:
        """
        Validate the area input and returns the area as a list of integers
        """
        area_list: list[int] = []
        if isinstance(area_input, str):
            area_input = re.sub(r'[ \t\r\n]', '', area_input)
            area_input = (re.sub(r'[＞﹥›˃ᐳ❯]', '>', area_input)).split('>')
            # tried to convert to set to remove duplicates but doesn't maintain order
            [area_list.append(x) for x in area_input if x not in area_list]    
        elif isinstance(area_input, int):
            area_list = [str(area_input)]

        if area_list and len([x for x in area_list if x.isdigit()]) == len(area_list):
            return [int(x) for x in area_list]
        else:        
            mode_name = "Normal" if mode == "N" else "Hard"
            logger.error(f"Failed to read Mission {mode_name}'s area settings")
            return None
            
    @property
    def mission_info(self) -> list[str, list[int], bool]:
        """
        Generate task, a list of list where each inner list is defined as
        [mode, area_list, completion_level] e.g ["H", [6,7,8], "clear"]
        """
        valid = True
        mode = ("N", "H")
        enable: tuple[bool] = (self.config.Normal_Enable, self.config.Hard_Enable)
        area: tuple[str] = (self.config.Normal_Area, self.config.Hard_Area)
        area_list: list[list[int]] = [None, None]
        completion_level: tuple[bool] = (self.config.Normal_Completion, self.config.Hard_Completion)

        for index in range(2):
            if enable[index]:
                area_list[index] = self.validate_area(mode[index], area[index]) 
                valid = valid if area_list[index] else False

        if valid:
            info = zip(mode, area_list, completion_level)
            return list(filter(lambda x: x[1], info))
        else:
            raise RequestHumanTakeover
        
    @property
    def stage_ap(self):
        if self.current_mode == "N":
            return 10
        return 20

    @property
    def current_mode(self):
        return self.task[0][0]

    @property
    def current_area(self):
        return self.task[0][1][0]
    
    @property
    def current_completion_level(self):
        return self.task[0][2] 
    
    def update_stages_data(self) -> bool:
        if [self.previous_mode, self.previous_area] != [self.current_mode, self.current_area]:
            self.stages_data = self.get_stages_data(self.current_mode, self.current_area)
        if self.stages_data:
            return True
        return False
    
    def find_alternative(self, type: str, preset_list: list[list[int, int]]) -> list[list[int, int]]:
        if not self.config.cross_get("Settings.Formation.Substitute"):
            return None
        
        alternatives_dictionary = {
            'pierce1': ['pierce2', 'burst1', 'burst2', 'mystic1', 'mystic2'],
            'pierce2': ['burst1', 'burst2', 'mystic1', 'mystic2'],
            'burst1': ['burst2', 'pierce1', 'pierce2', 'mystic1', 'mystic2'],
            'burst2': ['pierce1', 'pierce2', 'mystic1', 'mystic2'],
            'mystic1': ['mystic2', 'burst1', 'burst2', 'pierce1', 'pierce2'],
            'mystic2': ['burst1', 'burst2', 'pierce1', 'pierce2'],
        }
        alternatives = alternatives_dictionary[type]
        for alternative in alternatives:
            alternative_preset = self.default_type_to_preset[alternative]
            if alternative_preset not in preset_list:
                preset_list.append(alternative_preset)
                logger.warning(f"{type} was replaced by {alternative}")
                return preset_list
        logger.error(f"Unable to find replacements for {type}")
        return None
    
    def update_current_type_to_preset(self) -> bool:
        if [self.previous_mode, self.previous_area] == [self.current_mode, self.current_area]:
            # set it to None. This will skip changing preset in self.formation
            self.current_type_to_preset = None
            return True

        mode_name = "Normal" if self.current_mode == "N" else "Hard"
        use_alternative = False
        for stage, info in self.stages_data.items():
            if "start" not in info:
                continue

            list_preset: list[list[int, int]] = []
            list_type : list[str] = []
            for type in info["start"]:
                preset = self.default_type_to_preset[type]
                list_type.append(type)

                if preset not in list_preset:
                    list_preset.append(preset)
                    continue
                logger.error(f"Mission {mode_name} {self.current_area} requires {list_type} but they are both set to preset {preset}")
                list_preset = self.find_alternative(type, list_preset)
                use_alternative = True
                if list_preset:
                    continue                
                return False

            if use_alternative:
                alt_type_to_preset: dict[str, list[list[int, int]]] = {}
                for index in range(len(list_type)):
                    type, preset = list_type[index],  list_preset[index]
                    alt_type_to_preset[type] = preset
                self.current_type_to_preset = alt_type_to_preset
            else:
                self.current_type_to_preset = self.default_type_to_preset
            return True
        
        return False
    
    def update_task(self):
        self.previous_mode = self.current_mode
        self.previous_area = self.current_area
        area_list = self.task[0][1]
        area_list.pop(0)
        if not area_list:
            self.task.pop(0)
        
    def handle_auto_mission(self, status):
        match status:
            case AutoMissionStatus.AP:
                if self.task:
                    self.realistic_count = self.get_realistic_count(desired_count=1)
                    if self.realistic_count != 0:
                        return AutoMissionStatus.STAGES_DATA
                return AutoMissionStatus.FINISH
            
            case AutoMissionStatus.STAGES_DATA:
                if self.update_stages_data() and self.update_current_type_to_preset():
                    return AutoMissionStatus.NAVIGATE
                return AutoMissionStatus.END
            
            case AutoMissionStatus.NAVIGATE: 
                self.navigate(self.previous_mode, self.current_mode)
                if self.select_area(self.current_area) and self.select_mode(self.current_mode):
                    return AutoMissionStatus.ENTER
                return AutoMissionStatus.END
                        
            case AutoMissionStatus.ENTER:
                if self.wait_mission_info(self.current_mode, open_task=True):
                    return AutoMissionStatus.CHECK
                return AutoMissionStatus.END
            
            case AutoMissionStatus.CHECK:
                self.current_stage: Stage = self.check_stages(
                    self.current_mode, self.current_area, self.stages_data, self.current_completion_level
                    )
                if self.current_stage:
                    return AutoMissionStatus.START
                return AutoMissionStatus.END

            case AutoMissionStatus.START:
                self.start_stage(self.current_stage)
                return AutoMissionStatus.FORMATION
                                
            case AutoMissionStatus.FORMATION:
                self.formation(self.current_stage, self.current_type_to_preset)
                return AutoMissionStatus.FIGHT
            
            case AutoMissionStatus.FIGHT:
                self.fight(self.current_stage, manual_boss=self.config.ManualBoss_Enable)
                self.update_ap(1)
                self.previous_mode = self.current_mode
                self.previous_area = self.current_area
                return AutoMissionStatus.AP

            case AutoMissionStatus.END:
                self.update_task()
                return AutoMissionStatus.AP
                        
            case AutoMissionStatus.FINISH:
                return status
            
            case _:
                logger.warning(f'Invalid status: {status}')

        return status

    def run(self):
        self.task = self.mission_info
        if self.task:
            action_timer = Timer(0.5, 1)
            status = AutoMissionStatus.AP
            
            """Update the dashboard to accurately calculate AP"""
            self.ocr_ap()
            
            while 1:
                self.device.screenshot()

                if self.ui_additional():
                    continue

                if action_timer.reached_and_reset():
                    logger.attr('Status', status)
                    status = self.handle_auto_mission(status)

                if status == AutoMissionStatus.FINISH:
                    break
        else:
            logger.warning('Auto-Mission enabled but no task set')
            raise RequestHumanTakeover
        
        self.config.task_delay(server_update=True)
        