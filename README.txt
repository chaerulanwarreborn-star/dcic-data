DCIC Wizards' Hollow - final practical files

1. dcic-theme-new-wizards-home.xml
   Upload/apply this directly as the Blogger theme.

2. extract_wizards_hollow.py
   Put this in the root of the dcic-data repository.

3. side_events_config.json
   Put/update this in the root of the dcic-data repository.

4. .github/workflows/update-events.yml
   Replace the current workflow with this version.

The workflow generates wizards_hollow.json automatically.
No apply_wizards_home_to_theme.py or patch TXT is required for deployment.
