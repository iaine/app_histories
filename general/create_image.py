from glob import glob

import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.animation as animation

from PIL import Image
import numpy as np

class Animate():

    def __init__(self):
        pass

    def animate_images(self, base_dir, onscreen=1000, fmt="png"):
        """
            Method to create a video from still images
        """
        if base_dir is None or not os.path.exits(base_dir):
            raise Exception("Directory dies not exist")

        try:
            img = glob(base_dir +"/" + "*." + fmt)
            frames = []
            fig = plt.figure()
            for i in range(1,len(img)):
                _img = np.asarray(Image.open(img[i]))
                frames.append([plt.imshow(_img, animated=True)])

            ani = animation.ArtistAnimation(fig, frames, interval=onscreen, blit=True,
                                            repeat_delay=1000)
            ani.save(outfile)
        except Exception, e:
            print(e)
