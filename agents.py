import time
import torch
import math
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from src.color_detection import interpret_image
from src.Reinforce import Reinforce
from src.env import VrepEnvironment

import sys, os
sys.path.insert(1, os.path.join(sys.path[0], '..'))
import settings

if settings.draw_dist:
    plt.ion()
    plt.figure()

class PiCarX(object):
    def __init__(self, policy):
        self.env = VrepEnvironment(settings.SCENES + '/environment.ttt')
        self.env.connect() # Connect python to the simulator's remote API
        self.env.start_simulation()
        self.policy = policy
        
        # motors, positions and angles
        self.cam_handle = self.env.get_handle('Vision_sensor')
        self._motor_names = ['Pioneer_p3dx_leftMotor', 'Pioneer_p3dx_rightMotor']
        self._motor_handles = [self.env.get_handle(x) for x in self._motor_names]
        self.angular_velocity = np.zeros(2)
        self.angles = np.zeros(2)
        self.pos = [0, 0]
        self.change_velocity([2, 2])
        
    def current_speed(self):
        """
        Current angular velocity of the wheel motors in rad/s
        """
        prev_angles = np.copy(self.angles)
        self.angles = np.array([self.env.get_joint_angle(x, 'buffer') for x in self._motor_handles])
        angular_velocity = self.angles - prev_angles
        for i, v in enumerate(angular_velocity):
            # in case radians reset to 0
            if v < -np.pi:
                angular_velocity[i] =  np.pi*2 + angular_velocity[i]
            if v > np.pi:
                angular_velocity[i] = -np.pi*2 + angular_velocity[i]
        self.angular_velocity = angular_velocity
        return self.angular_velocity

    def current_speed_API(self):
        self.angular_velocity = np.array([self.env.get_joint_velocity(x, 'buffer') for x in self._motor_handles])
        return self.angular_velocity

    def change_velocity(self, velocities, target=None):
        """
        Change the current angular velocity of the robot's wheels in rad/s
        """
        if target == 'left':
            self.env.set_target_velocity(self._motor_handles[0], velocities)
        if target == 'right':
            self.env.set_target_velocity(self._motor_handles[1], velocities)
        else:
            [self.env.set_target_velocity(self._motor_handles[i], velocities[i]) for i in range(2)]
    
    def read_image(self, mode='blocking'):
        _, resolution, image = self.env.get_vision_image(self.cam_handle, mode)
        return image, resolution

    def detect_objects(self):
        img, res = self.read_image()
        img = np.array(img, dtype=np.uint8).reshape([res[1], res[0], 3])
        img = np.flip(img, axis=0)
        
        mask = interpret_image("green", "red", img)
        #image.save('images/img_dec.png')
        #print(image.shape)
        return mask
    
    def save_image(self, image, resolution, options, filename, quality=-1):
        self.env.save_image(image, resolution, options, filename, quality)
    
    def reset_env(self, use_API=True):
        if use_API:
            try:
                self.env.stop_simulation()
                self.env.disconnect()
            except: pass
            self.env.connect() # Connect python to the simulator's remote API
            self.env.start_simulation()
        else:
            try: self.env.stop_simulation()
            except: pass
            self.env.start_simulation()
        
    
    def move(self, movement, angle):
        # this function moves the robot in env and returns the reward achieved
        # returns also done
        speed = math.radians(angle)
        if np.random.choice([True, False], 1)[0]:
            if movement == 1:
                self.change_velocity([-speed, speed])
            else:
                self.change_velocity([-speed, 0])
        else:
            if movement == 1:
                self.change_velocity([speed, -speed])
            else:
                self.change_velocity([0, -speed])
        time.sleep(1)
        # TODO: implement reward system
        return 0, False
    
    def act(self, trials):
        r_ep = [0]*trials
        for i in range(trials):
            done = False
            self.reset_env()
            while not done:
                with torch.no_grad():
                    self.policy.eval()
                    s = self.detect_objects()
                    pred = self.policy.forward(s)
                    r, done = self.move(torch.argmax(pred.detach()).item())
                r_ep[i] += r
        return np.mean(r_ep)

    def train(self, epochs, M, T, gamma, ef=None, run_name=None):
        reinforce = Reinforce(self, epochs, M, T, gamma, ef, run_name)
        rewards = reinforce()
        return rewards
