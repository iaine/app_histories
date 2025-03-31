##  Language Presence in Apps

One way of using the localisation code is to create and use it to trace languages and apps over time. 

I used the localisation code to find the filenames that contain localisations patterns. 

Using some R an Python code yet to be released, I managed to extract the country nad languages. 

```
# First get the Androo Zoo list
archive_df = pd.read_csv("androzoo.csv")
archive_df.columns= ['sha','sha1','sha2','dexdate', 'apksize','package','?', 'virus','virusdate','!','market']
# Now to get the list of app and localisations
localised_df = pd.read_csv("local_found.csv")
localised_df.columns = ['sha', 'local']

#merge the two together to enable sorting later. 
merged_df = pd.merge(archive_df, localised_df, on="sha")
merged_df['language'] = merged_df['local'].map(Localisation().extract_language)
merged_df['country'] = merged_df['local'].map(Localisation().extract_country)
```

I filtered the data by country in a CSV file. In this case, I used IN, or India, as it has a range of languages. 

![All languages for an app ](../assets/meituan_language_country.png)

This provides a nice broad view of the territry. The data can be broken down further. In this case, I broke it down by major version number of the app as extracted while reading the permission from the manifests. 

![A Composite Image of Versions of an App with its languages](../assets/composite.jpg)

This offers many more different forms of reading that require further investigation. 