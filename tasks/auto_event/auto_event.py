from tasks.mission.ui import MissionUI
from tasks.stage.ap import AP
from tasks.stage.stage import StageState, Stage
from tasks.auto_event.ui import AutoEventUI
from enum import Enum

from module.base.timer import Timer
from module.exception import RequestHumanTakeover
from module.logger import logger

class AutoEventStatus(Enum):
    AP = 0 # Calculate AP and decide to terminate Auto-Mission module or not
    NAVIGATE = 1 # Navigate to the area and select mode
    ENTER = 2 # Enter the first stage in the stage list
    CHECK = 3 # Check stages and find a stage that requires to be completed
    START = 4 # Start the stage
    STORY = 5
    FORMATION = 6 # Select units based on the types required by the stage
    FIGHT = 7 # Fight the stage
    END = 8 # Update task
    FINISH = -1 # Indicate termination of Auto-Mission module

class AutoEvent(AP, MissionUI, AutoEventUI):  
    def __init__(self, config, device):
        super().__init__(config, device) 
        self.task: list[str, list[int], bool] = None
        self.previous_mode: str = None
        self.current_stage: Stage = None
        self.default_type_to_preset: dict = self.get_default_type_to_preset()

    @property
    def stage_ap(self):
        if self.current_mode == "S":
            return 10
        if self.current_stage.name >= "09":
            return 20
        elif self.current_stage.name <= "04":
            return 10
        else:
            return 15

    @property
    def event_info(self) -> list[str, bool, bool]:
        """
        Generate task, a list of list where each inner list is defined as
        [mode, area_list, completion_level] e.g ["H", [6,7,8], "clear"]
        """
        mode = ("ES", "E")
        enable: tuple[bool] = (self.config.EventStory_Enable, self.config.EventQuest_Enable)
        completion_level: tuple[bool] = (self.config.Normal_Completion, self.config.Hard_Completion)
        info = zip(mode, enable, completion_level)
        return list(filter(lambda x: x[1], info))
    
    @property
    def current_mode(self):
        return self.task[0][0]
    
    def current_completion_level(self):
        return self.task[0][2]
    
    def handle_auto_event(self, status):
        match status:                        
            case AutoEventStatus.NAVIGATE: 
                self.navigate(self.previous_mode, "E")
                self.previous_mode = "E"
                if self.select_mode(self.current_mode):
                    return AutoEventStatus.ENTER
                return AutoEventStatus.END
                        
            case AutoEventStatus.ENTER:
                if self.wait_event_info(open_task=True):
                    return AutoEventStatus.CHECK
                return AutoEventStatus.END
            
            case AutoEventStatus.CHECK:
                self.current_stage: Stage = self.check_stages(self.current_mode, self.current_completion_level)
                if self.current_stage:
                    return AutoEventStatus.AP
                return AutoEventStatus.END

            case AutoEventStatus.AP:
                self.realistic_count = self.get_realistic_count(desired_count=1)
                if self.realistic_count != 0:
                    return AutoEventStatus.START
                return AutoEventStatus.FINISH
            
            case AutoEventStatus.START:
                self.start_stage(self.current_stage)
                if self.current_stage.state == StageState.EPISODE:
                    return AutoEventStatus.STORY
                return AutoEventStatus.FORMATION
            
            case AutoEventStatus.STORY:
                self.skip_story()
                return AutoEventStatus.ENTER
                                
            case AutoEventStatus.FORMATION:
                self.formation(self.current_stage, self.default_type_to_preset)
                return AutoEventStatus.FIGHT
            
            case AutoEventStatus.FIGHT:
                self.fight(self.current_stage, manual_boss=False)
                self.update_ap(1)
                return AutoEventStatus.ENTER

            case AutoEventStatus.END:
                self.task.pop(0)
                if not self.task:
                    return AutoEventStatus.FINISH
                return AutoEventStatus.NAVIGATE
                        
            case AutoEventStatus.FINISH:
                return status
            
            case _:
                logger.warning(f'Invalid status: {status}')

        return status

    def run(self):
        self.task = self.event_info
        if self.task:
            action_timer = Timer(0.5, 1)
            status = AutoEventStatus.NAVIGATE
            
            """Update the dashboard to accurately calculate AP"""
            self.ocr_ap()
            
            while 1:
                self.device.screenshot()

                if self.ui_additional():
                    continue

                if action_timer.reached_and_reset():
                    logger.attr('Status', status)
                    status = self.handle_auto_event(status)

                if status == AutoEventStatus.FINISH:
                    break
        else:
            logger.warning('Auto-Event enabled but no task set')
            raise RequestHumanTakeover
        
        self.config.task_delay(server_update=True)
        