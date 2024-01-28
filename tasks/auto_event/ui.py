from module.logger import logger
from tasks.stage.copilot import Copilot
from tasks.stage.stage import StageState, Stage
from tasks.stage.assets.assets_stage_copilot import MOBILIZE
from tasks.stage.assets.assets_stage_enemies import *
from tasks.stage.assets.assets_stage_sweep import ENTER, ONE_STAR, THREE_STARS

import cv2
import numpy as np

class AutoEventUI(Copilot):
    """
    Class dedicated to navigate the mission page and check stages
    """
    def wait_event_info(self, open_task=False, max_retry=99999):
        while max_retry > 0:
            self.device.screenshot()
            # Main task
            if self.appear(ENTER):
                return 'main'
            # Open the task if needed
            if open_task:
                for i in range(3):
                    self.device.swipe((917, 220), (917, 552))
                self.sleep(1)
                #click enter
                self.click(1118, 200)
                #self.sleep(1)
            max_retry -= 1
        logger.error("max_retry {0}".format(max_retry))
        return None    
    
    def check_stage_state(self) -> StageState:
        """
        Check the current stage type
        """
        # Wait for the task information popup to load
        self.wait_event_info()
        self.sleep(1)
        self.device.screenshot()
        # Main task - Three stars
        if self.match_color(THREE_STARS):
            return StageState.SSS
        # Not cleared
        if self.match_color(ONE_STAR):
            return StageState.CLEARED
        # Main task - Cleared
        return StageState.UNCLEARED
                
    def check_enemies(self):
        enemies_count = {"burst1": 0, "pierce1": 0, "mystic1": 0}
        enemies_button = {"burst1": LIGHT, "pierce1": HEAVY, "mystic1": SPECIAL}
        self.select_then_check(ENEMIES, ENEMIES_POPUP)
        for type, button in enemies_button.items():
            result = cv2.matchTemplate(self.device.image, button.matched_button.image, cv2.TM_CCOEFF_NORMED)
            threshold = 0.8
            locations = np.where(result >= threshold)
            enemies_count[type] = len(locations[0])
        self.select_then_check(ENEMIES_POPUP, ENEMIES)
        return {"EVENT" : max(enemies_count, key=enemies_count.get)}

    def check_stages(self, mode, completion_level) -> Stage:
        """
        Find the stage that needs to be battled
        """
        stage_index = 1
        max_index = 9 if mode == "ES" else 12
        found = False
        while 1:
            # Wait for the task information to load
            stage_state = self.check_stage_state()
            logger.info("Current stage status: {0}".format(stage_state))
            stage_name = str(stage_index) if stage_index >= 10 else f"0{stage_index}"
            # Not cleared main task
            if stage_state == StageState.UNCLEARED:
                logger.warning(f"{stage_name} Not cleared main stage, starting battle...")
                found = True
            # Mode 2 ⭐️⭐️⭐️ or ⭐️⭐️⭐️ + box gift
            elif completion_level == "three_stars" and stage_state != StageState.SSS:
                logger.warning(f"{stage_name} Not three-star cleared, starting battle...")
                found = True
            if found:
                stage_info = self.check_enemies()
                if not stage_info:
                    logger.error(f"Exploration not supported for the stage {stage_name}, under development...")
                    return None
                else:
                    return Stage(stage_name, StageState.EVENT, stage_info)
            # Click on the next stage
            logger.info(f"{stage_name} already meets specified completion level, searching for the next stage")
            self.click(1172, 358, interval=0)
            # Check if still in the same region
            stage_index += 1
            if stage_index >= max_index:
                return None
    
    def start_stage(self):
        # Click to start the task
        self.select_then_check(ENTER, MOBILIZE)
