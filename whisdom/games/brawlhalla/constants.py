"""Brawlhalla-specific constants. Everything here is game knowledge."""
XOR_KEY=[107,16,222,60,68,75,209,70,160,16,82,193,178,49,211,106,251,172,17,222,6,104,8,120,
         140,213,179,249,106,64,214,19,12,174,157,197,212,107,84,114,252,87,93,26,6,115,194,81,
         75,176,201,140,120,4,17,122,239,116,62,70,57,160,199,166]
FPS=60
MS_PER_FRAME=1000.0/FPS
# verified against a scripted-input control replay
INPUT_BITS={0:"AimUp",1:"AimDown",2:"Left",3:"Right",4:"Jump",5:"UpJump",
            6:"Heavy",7:"Light",8:"Dodge",9:"ThrowPickup"}
# how long an action occupies the player (frames) - from extracted game data
DODGE_DURATION=14
DODGE_COOLDOWN=163
ATTACK_MIN_GAP=8
CATEGORIES={"attack":["Light","Heavy"],"movement":["Left","Right"],
            "defence":["Dodge"],"mobility":["Jump","UpJump"],"utility":["ThrowPickup"]}
