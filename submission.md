# Mixtape Bug Hunt — System Submission Document

## 🤖 AI Usage Framework

### Instance 1: Initial System Navigation and Data Flow Mapping
* **What I Directed the AI to Do**: I provided the initial database models from `models.py` and asked for a step-by-step trace of how the symmetric relationship properties behave under the hood, specifically focusing on how the `playlist_entries` join table manages explicit ordering metrics.
* **What the AI Produced**: It generated a breakdown mapping the relationships between users, songs, and playlists.
* **What I Revised or Overrode**: The initial explanation assumed standard array appending logic for relations. However, my local linter threw missing import diagnostics. I had to manually re-configure the workspace path interpreter using `Select Interpreter` to bind against my active `.venv` environment so I could visually trace variables myself.

### Instance 2: Debugging the Automated Regression Test Constraints
* **What I Directed the AI to Do**: I asked for a testing routine to prevent the truncation of playlist songs, utilizing the `app` database context structures.
* **What the AI Produced**: It provided a test signature that accepted both `app` and `client` fixtures, using `User.query.first()` to fetch sample records.
* **What I Revised or Overrode**: Running the test suit caused crashes. First, it triggered a missing fixture error because a `client` handler didn't exist in the project suite. Second, running it inside an isolated database environment caused `User.query.first()` to return a `NoneType` object. Finally, calling the standard append helper triggered an `IntegrityError` because it left the strict `NOT NULL` constraints on the `position` and `added_by` columns completely blank. I completely rewrote the execution block, removing the unneeded client parameter, seeding a distinct mock user structure, and using explicit `db.session.execute(playlist_entries.insert())` loops to populate the table parameters manually.

---

## 🗺️ Codebase Map & Architecture Overview

### Main Component Definitions

#### Core Application Controllers
* **`app.py`**: The central application factory configuration. It initializes the SQLAlchemy instance, registers the primary blueprints (`/songs`, `/playlists`, `/users`, `/feed`), and bootstraps the relational database structure within the active context layer.
* **`models.py`**: Contains the data layer blueprints for all 7 database entities using SQLAlchemy. It establishes relational constraints and tracking variables:
    * `User`: Tracks user accounts, profile details, and baseline listening stats (`listening_streak`, `last_listened_at`).
    * `Song`: Models shared music metadata alongside personal notes from the initial creator.
    * `Playlist`: Tracks user-curated track listings that can optionally toggle collaborative write permissions.
    * `ListeningEvent`: Logs time-stamped history rows whenever an author plays a track.
    * `Rating`: Holds score values (1–5) and enforces a unique constraint preventing double-rating.
    * `Notification`: Stores system updates and alerts mapped to target recipient IDs.
    * `Tag`: Simple category strings used to classify tracks.
* **`playlist_entries` (Join Table)**: A structural association table linking playlists and songs. Crucially, it manages an explicit `position` column to preserve track ordering, along with metadata tracks for who added the track and when.
* **`friendships` & `song_tags`**: Pure association lookup tables handling symmetric many-to-many bonds across users and track metadata.

#### Routing Layers (`routes/`)
* **`songs.py` / `playlists.py` / `users.py` / `feed.py`**: These modules act as thin API gateways. Their sole responsibility is handling input parsing, decoding JSON payload fragments, verifying baseline field presence, and mapping downstream outputs into clean HTTP responses.

#### Business Logic Engines (`services/`)
* **`feed_service.py`**: Rebuilds user timelines, handling track sorting arrays and populating what content should display.
* **`playlist_service.py`**: Manages playlist state mutations, including order sorting, collaborator checking, and track insertions.
* **`streak_service.py`**: Tracks user app engagement and updates user engagement trends over time.
* **`notification_service.py`**: Coordinates multi-action alert pipelines across the system.
* **`search_service.py`**: Processes search lookups and coordinates database filtering across songs and tags.

---

### Architectural Design Patterns
The application enforces strict **Separation of Concerns**. Routes never touch database queries or execute algorithmic transitions directly. They validate data shapes and instantly pass execution down to the `services/` layer. The service layer handles all state verification, calculations, and mutations before handing clean object models back to the routing endpoints for JSON rendering.

---

### End-to-End System Data Flow Example
When a user listens to a song, the lifecycle flows through the platform layers along this path:

```text
[Client App POST /users/listen] 
               │
               ▼
   [routes/users.py Endpoint] ──► Extracts user_id & song_id from payload
               │
               ▼
 [services/streak_service.py] ──► Calculates current streak changes relative to last_listened_at
               │
               ▼
   [models.py Database Commit] ──► Writes a new ListeningEvent record
                               ──► Updates the User table row with new streak count
               │
               ▼
  [Client App 200 OK Response] ◄── Returns updated user stats dictionary
```

---

## 🐛 Root Cause Analysis Ledger

### Issue #5: The last song in a playlist never shows up
* **How you reproduced it**: Ran `pytest tests/test_playlists.py` in the terminal. The test suite failed on playlist retrieval because the returned song count was short by exactly 1 element compared to the setup data.
* **How you found the root cause**: Traced the endpoint from `routes/playlists.py` into `services/playlist_service.py`. Inspected the return statement of `get_playlist_songs()` and identified an active list slice operation truncating the dataset.
* **The root cause**: The function utilized a Python list slice (`songs[:-1]`) on the query results. This slice explicitly drops the last item from the array collection, meaning the final song in any playlist layout was omitted from the payload returned to the frontend template.
* **Your fix and side-effect check**: Removed the `[:-1]` slice from the return comprehension statement to let the array return naturally. Verified that other playlist modules like metadata lookups (`get_playlist()`) or collection maps (`get_user_playlists()`) were unaffected, as they do not manipulate track indices.

### Issue #3: The same song keeps showing up twice in search
* **How you reproduced it**: I simulated search queries using the test suite by running `python -m pytest tests/test_search.py`. The execution failed because songs containing multiple tag associations returned duplicate items inside the search results list.
* **How you found the root cause**: I opened `services/search_service.py` and reviewed the query logic inside `search_songs()`. I saw an explicit `.outerjoin(song_tags)` tracking against the song tags database, which immediately signaled that relational row multiplying was happening.
* **The root cause**: The query used an `outerjoin` on the `song_tags` association table. When a track has more than one tag, the database generates multiple joined rows for that single song ID. SQLAlchemy pulls all matching rows into memory, causing the same track to repeat inside the output array.
* **Your fix and side-effect check**: I appended `.distinct()` directly to the SQLAlchemy query chain to force the database to deduplicate the row objects based on their unique primary keys. I then verified that the tags still render properly via `song.to_dict()` and confirmed the test suite passes cleanly.

### Issue #4: I got notified when a friend added my song to a playlist but not when they rated it
* **How you reproduced it**: I verified the behavior by checking the database notifications table after running a mock song rating scenario. No alert entries were generated for the target creator ID.
* **How you found the root cause**: I opened `services/notification_service.py` and compared the operational structure of `add_to_playlist()` against `rate_song()`. I saw that while the playlist module explicitly called `create_notification()`, the rating logic completely skipped this step.
* **The root cause**: The `rate_song()` logic calculated and saved the updated score parameters to the database correctly, but it completely lacked any system hooks to execute a notification event. It failed to check if the rater was different from the original creator and never invoked the notification generator.
* **Your fix and side-effect check**: I added a conditional check right before the database commit to confirm that if a user rates a song shared by someone else, it triggers `create_notification()` with the type set to 'song_rated'. I then confirmed that rating your own songs doesn't trigger a self-notification loop.

### Issue #1: My listening streak keeps resetting
* **How you reproduced it**: I ran the streak test file using `python -m pytest tests/test_streaks.py`. The assertions failed specifically on test routines tracking consecutive day check-ins on Sundays.
* **How you found the root cause**: I examined `services/streak_service.py` and traced how the application counts days inside `update_listening_streak()`. I noticed a hardcoded condition checking `today.weekday() != 6` on the increment path.
* **The root cause**: The code used Python's `weekday()` method, which represents Sunday as `6`. Because the increment check required `today.weekday() != 6`, any listen event occurring on a Sunday failed the conditional requirement. This pushed the user's account into the fallback `else` block, resetting active streaks back to `1` every Sunday night even if they had listened on Saturday.
* **Your fix and side-effect check**: I removed the `and today.weekday() != 6` statement entirely, allowing any consecutive daily event (`days_since_last == 1`) to increment the count naturally. I ran the streak test suite again to confirm same-day multiple listen events still correctly exit without double-counting.

### Issue #2: Friends Listening Now shows people from yesterday
* **How you reproduced it**: I inspected the baseline data configuration and noticed that running a mock query returned user tracking events that occurred up to 24 hours in the past instead of filtering for live presence.
* **How you found the root cause**: I opened `services/feed_service.py` and examined the `get_friends_listening_now()` algorithm. I looked at the top of the module where the lookup boundaries are configured and identified the `RECENT_THRESHOLD` value.
* **The root cause**: The code defined `RECENT_THRESHOLD` as a 24-hour time delta (`timedelta(hours=24)`). This meant that the database query for a live "Listening Now" component was pulling every tracking record from the past day, causing friends who finished listening to music yesterday to stay stuck in the active feed.
* **Your fix and side-effect check**: I changed the `RECENT_THRESHOLD` constant value to 5 minutes (`timedelta(minutes=5)`). This constrains the query to active users. I then verified that the general `get_activity_feed()` function remains unchanged, as it is designed to show historical listings without a time boundary.

---

## 🧪 Regression Test Reference

I have implemented an isolated, dedicated automated regression testing suite located within a new standalone file at `tests/test_regression.py`. This suite provides explicit documentation and guards against the regression of fixed boundary conditions:

1. `test_playlist_returns_all_songs_including_the_last_one(app)`: This test sets up a 3-track playlist and verifies that the returned array matches the expected count. Under the original buggy implementation, the array slice would truncate the final track and cause this test to fail.
2. `test_streak_increments_saturday_to_sunday(app)`: This test explicitly isolates the calendar boundary change between a Saturday and Sunday check-in. It ensures that the sequence increments an active user's listening streak to 2 rather than dropping into the erroneous fallback branch that reset it to 1.
