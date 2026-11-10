on run argv
    set appPath to item 1 of argv
    set jsxFile to (POSIX file (item 2 of argv)) as alias
    with timeout of 120 seconds
        tell application appPath
            activate
            delay 0.2
            -- Illustrator's installed scripting dictionary: do javascript = misc/DjxM.
            -- Raw event notation avoids LaunchServices dictionary lookup at compile time.
            return «event miscDjxM» jsxFile
        end tell
    end timeout
end run

