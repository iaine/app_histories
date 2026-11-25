"""
This is the "helpers" module.

It contains a helper function for post-processing
"""
import pandas as pd

class Helper():

    def __init__(self):
        pass

    def list_difference(self, a,b):
        return int(len(list(set(a.split(';')) - set(b.split(';')))))

    def permissions_changes(self, df, data_category, added, removed):
        """
            Get a list of the addition / deletions from permissions

            :param df - the pandas dataframe with the data
            :param data_category
            :param added - column added
            :param removed - column removed

            :return permissions_df
        """

        permissions_df = df[['version_code', data_category]].sort_values('version_code').reset_index(drop=True)

        permissions_df.loc[0, added] = 0
        permissions_df.loc[0, removed] = 0
        for i in range(1, len(permissions_df)):
            permissions_df.loc[i, added] = self.list_difference(permissions_df.loc[i-1, data_category], permissions_df.loc[i, data_category])
            permissions_df.loc[i, removed] = 0-self.list_difference(permissions_df.loc[i, data_category], permissions_df.loc[i-1, data_category])

        return permissions_df

    def get_launchers(self, df):
        """
        Code to get laucnher permissions

        :param df - dataframe

        :return launced_df 
        """

        launcher_permissions = (
            df.assign(
                permission=df["permissions"].str.split(";")
            )
            .explode("permission")
        )

        launcher_permissions["permission"] = (
            launcher_permissions["permission"].str.strip()
        )

        launcher_permissions = launcher_permissions[
            launcher_permissions["permission"].str.contains(
                "launcher",
                case=False,
                na=False
            )
        ][["permission", "version_code"]]

        return launcher_permissions

    def flatten_list(flist, country=""):
        if country != "":
            return ','.join(list(set( [lang[0] for lang in flist if lang[1] == country] )))
        else:
            return ','.join(list(set( [lang[0] for lang in flist])))

    def country_lang(flist, language=""):
        return ','.join(list(set( [lang[1] for lang in flist if lang[0] == language] )))

    def localisation(self, df, lang = "en", country=""):
        """
            Find language in df
        """

        localisation_df = df[['version_code', 'localisation']].sort_values('version_code').reset_index(drop=True)

        if country:
            localisation_df['flattened'] = localisation_df['localisation'].apply(country, language=lang)


        # Split language strings into lists
        localisation_df["languages"] = (
            localisation_df["flattened"]
            .fillna("")
            .str.split(",")
            .apply(lambda x: [i.strip() for i in x if i.strip()])
        )

        # Convert to long format
        lang_df = (
            localisation_df[["version_code", "languages"]]
            .explode("languages")
            .rename(columns={"languages": "language"})
            .reset_index(drop=True)
        )

        # Remove blanks
        lang_df = lang_df[lang_df["language"].notna()]

        # Build presence matrix
        presence = pd.crosstab(
            lang_df["language"],
            lang_df["version_code"]
        ).astype(bool)

        # Order languages by first appearance
        first_seen = {
            lang: min(presence.columns[presence.loc[lang]])
            for lang in presence.index
        }

        presence = presence.loc[
            sorted(presence.index, key=lambda x: first_seen[x])
        ]


    def list_similarity(self, dict_of_lists):
        '''
        Functions to compare lists to determine changes.
        Run this for post-processing as it relies on a list
        of permissions, activities, or intents to be present
        :param dict_of_lists - dictionary of lists

        NB: this code relies on a previous sorting of the data into
        chronological order. software version may help here. 
        '''
        previous = None
        changes = {}
        for label, items in dict_of_lists.items():
            current = set(items)
            if previous is None:
                changes[label] = {"added": sorted(current), "removed": []}
            else:
                changes[label] = {
                    "added": sorted(current - previous),
                     "removed": sorted(previous - current),
                }
            previous = current
        return changes
            