from glob import glob

import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.animation as animation

from PIL import Image
import numpy as np

class Animate():

    def __init__(self):
        pass

    def animate_images(self, image_list, outfile, onscreen=1000, fmt="png"):
        """
            Method to create a video from still images
        """
        if base_dir is None or not os.path.exits(base_dir):
            raise Exception("Directory dies not exist")

        try:
            frames = []
            fig = plt.figure()
            for i in range(1,len(image_list)):
                _img = np.asarray(Image.open(image_list[i]))
                frames.append([plt.imshow(_img, animated=True)])

            ani = animation.ArtistAnimation(fig, frames, interval=onscreen, blit=True,
                                            repeat_delay=1000)
            ani.save(outfile)
        except Exception as e:
            print(e)

    def create_composite(self,imagedata, figuretitle, nrow=2, ncol=3):
        """
        Create composite grid
        """

        from mpl_toolkits.axes_grid1 import ImageGrid

        fig = plt.figure(figsize=(60., 60.))
        grid = ImageGrid(fig, 111,  # similar to subplot(111)
                        nrows_ncols=(nrow, ncol),  # creates 2x2 grid of Axes
                        axes_pad=0.1,  # pad between Axes in inch.
                        )

        for ax, im in zip(grid, imagedata):

            if type(im) == str:
                raise Exception("Incorrect format. Image data required")
                
            # Iterating over the grid returns the Axes.
            ax.imshow(im)
            # Let's remove the individual axis
            ax.set_axis_off()

        plt.savefig(figuretitle)    