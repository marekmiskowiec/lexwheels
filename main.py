from bs4 import BeautifulSoup
import requests
import pandas as pd
import openpyxl

# Environment settings:
pd.set_option('display.max_column', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.max_seq_items', None)
pd.set_option('display.max_colwidth', 500)
pd.set_option('expand_frame_repr', True)


url = 'https://hotwheels.fandom.com/wiki/List_of_2022_Hot_Wheels'

data = requests.get(url).text

soup = BeautifulSoup(data, 'html.parser')
#print(soup.prettify())

# Creating list with all tables
# tables = soup.find_all('table', class_='sortable wikitable')
# print(tables)

#  Looking for the table with the classes 'wikitable' and 'sortable'
table = soup.find('table', class_='sortable wikitable')

# Defining of the dataframe
df = pd.DataFrame(columns=['Number', 'Model Name', 'Series', 'Series Number', 'Photo'])

# Collecting Data
#for i in range(len(tables)):
for row in table.tbody.find_all('tr'):
    # Find all data for each column
    columns = row.find_all('td')

    if columns:
        #package = columns[0].text.strip()
        car_number = columns[1].text.strip()
        model_name = columns[2].text.strip()
        series = columns[3].text.strip()
        series_number = columns[4].text.strip()
        photo = columns[5].text.strip()

        # Get the link to the photo
        photo_tag = columns[5].find('a')
        # Check if the 'alt' attribute is present and equals 'image not available'
        alt_text = photo_tag.find('img')['alt'] if photo_tag and photo_tag.find('img') else None
        photo = photo_tag['href'] if photo_tag and alt_text != 'image not available' else None



        # Use pd.concat() to concatenate DataFrames
        df = pd.concat([df, pd.DataFrame({'Number': [car_number], 'Model Name': [model_name],
                                          'Series': [series], 'Series Number': [series_number],
                                          'Photo': [photo]})], ignore_index=True)

# Save DataFrame to Excel file
df.to_excel('hot_wheels_data.xlsx', index=False)