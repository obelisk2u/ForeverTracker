-- Runs once, on first initialisation of the development volume.
-- The test suite uses its own database so `pytest` never touches development data.
CREATE DATABASE forevertracker_test OWNER forevertracker;
