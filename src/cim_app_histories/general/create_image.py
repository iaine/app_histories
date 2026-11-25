from glob import glob

import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.animation as animation

from PIL import Image
import numpy as np

import seaborn as sns

class Animate():

    def __init__(self):
        pass

    def animate_images(self, image_list, outfile, onscreen=1000, fmt="png"):
        """
            Method to create a video from still images
        """
        
        try:
            frames = []

            fig, ax = plt.subplots()
            ax.set_axis_off()
            for i in range(1,len(image_list)):
                
                _img = np.asarray(Image.open(image_list[i]))
                frames.append([plt.imshow(_img, animated=True)])

            ani = animation.ArtistAnimation(fig=fig, artists=frames, interval=onscreen)
            ani.save(outfile)
            #if gif required
            #ani = animation.FuncAnimation(fig, frames, interval=40, blit=True, repeat=True, frames=100) 
            #ani.save(outfile, dpi=300, writer=animation.PillowWriter(fps=25))
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
                raise Exception("Incorrect format. Image data required not its path")

            # Iterating over the grid returns the Axes.
            ax.imshow(im)
            # Let's remove the individual axis
            ax.set_axis_off()

        plt.savefig(figuretitle)    

    def visualise_changes(self, permissions_df, added, removed, figurepath):
        """
            Scatterplot of the changes for permissions

            :param permissions_df
            :param added - added column
            :param removed - removed column
            :param figure path
        """

        ax = plt.subplots()
        ax = sns.barplot(x=permissions_df["version_code"], y=permissions_df[added], color='b')
        ax = sns.barplot(x=permissions_df["version_code"], y=permissions_df[removed], color='r')
        plt.xticks(rotation=45)
        plt.savefig(figurepath)

    def visualise_launchers(self, launcher_permissions):

        sns.scatterplot(launcher_permissions, x="version_code", y="permission")

    def visualise_langs(self, presence, fpath):
        """
        Visualise language links over time

        :param presence - language dataframe
        :param fpath - file path to save figure
        """
        # Plot
        fig, ax = plt.subplots(figsize=(16, max(8, len(presence) * 0.25)))

        for i, lang in enumerate(presence.index):

            versions_present = list(
                presence.columns[presence.loc[lang]]
            )

            ax.scatter(
                versions_present,
                [i] * len(versions_present),
                s=50,
                zorder=3
            )

            if len(versions_present) > 1:
                ax.plot(
                    versions_present,
                    [i] * len(versions_present),
                    linewidth=2,
                    alpha=0.7,
                    zorder=2
                )

        ax.set_yticks(range(len(presence.index)))
        ax.set_yticklabels(presence.index)

        ax.set_xlabel("Version")
        ax.set_ylabel("Language")
        ax.set_title("Language Support Across Releases")

        plt.xticks(rotation=45)
        plt.grid(axis="x", alpha=0.2)

        plt.tight_layout()
        plt.savefig(fpath)

    def visualise_langauge_heat(self, presence, fpath):
        """
            heatmap of languaages
        """

        sns.heatmap(
            presence.astype(int),
            cmap=["white", "#2166ac"],
            cbar=False,
            linewidths=0.1
        )

        plt.title("Language Availability Across Versions")
        plt.xlabel("Version")
        plt.ylabel("Language")
        plt.tight_layout()
        plt.savefig(fpath)