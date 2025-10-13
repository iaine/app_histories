import pandas as pd

from localisation.localisation import Localisation

archive_df = pd.read_csv("/Users/iain/Documents/projects/superapp_sprint/trackers/tracker_com.sankuai.meituan.csv")
archive_df.columns= ['sha','sha1','sha2','dexdate', 'apksize','package','?', 'virus','virusdate','!','market']
localised_df = pd.read_csv("/Users/iain/Documents/projects/superapp_sprint/localisation_meituan/local_found.csv")
localised_df.columns = ['sha', 'local']

merged_df = pd.merge(archive_df, localised_df, on="sha")
merged_df['language'] = merged_df['local'].map(Localisation().extract_language)
merged_df['country'] = merged_df['local'].map(Localisation().extract_country)
