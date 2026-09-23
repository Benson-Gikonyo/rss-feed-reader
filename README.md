# DevProjects - RSS feed reader in terminal

This is an open source project from [DevProjects](http://www.codementor.io/projects). Feedback and questions are welcome!
Find the project requirements here: [RSS feed reader in terminal](https://www.codementor.io/projects/tool/rss-feed-reader-in-terminal-atx32jp82q)

## Tech/framework used
Built with Flask, Sqlite and  bootstrap

## Screenshots and demo
Screenshots of your app and/or a link to your live demo
![Screenshot (45)](https://github.com/user-attachments/assets/0d6f751d-b0a3-40c5-a487-2f808993de6d)
![Screenshot (46)](https://github.com/user-attachments/assets/db8c0b89-9288-485c-b087-284a402ea176)
![Screenshot (47)](https://github.com/user-attachments/assets/754317b8-e449-407d-87e8-c689feee3713)


## Installation
clone the repository to your local machine
create a virtual enviroment:

```
python3 -m venv venv
```

```
source venv/bin/activate
```
install the requirements:

```
pip install -r requirements.txt
```
create your local environment file and replace the placeholder secret:

```
cp .env.example .env
```
Initialize the database before the first run:

```bash
flask --app rss_reader:create_app init-db
```

The database is stored at `instance/rss_feeds.db`. Importing modules or creating
an app does not initialize it. Connections use the app's `DATABASE` configuration
and close when the application context ends. Tests can override this path.

`init-db` preserves existing records and repairs the old articles foreign key to
reference `feeds`, with cascading deletion. If legacy articles reference missing
feeds, initialization fails and rolls back rather than deleting those records.

To retain an old repository-root `rss_feeds.db`, stop the app, back up the file,
and copy it to `instance/rss_feeds.db` before initialization. Do not overwrite an
existing instance database. Legacy subscriptions retain their stored URLs; if one
contains a website URL rather than the RSS URL, re-add the RSS URL to refresh it.
New subscriptions store the submitted RSS URL.

Run the application:

```
python3 app.py
```




## License
[MIT](https://choosealicense.com/licenses/mit/)


## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use temporary databases and mocked feeds; they do not touch local feed data.
