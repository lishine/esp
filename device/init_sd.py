import uos, machine


def init_sd():
    # --- SD Card Initialization ---
    SD_MOUNT_POINT = "/sd"  # Changed mount point name
    sd_mounted = False
    sd = None  # Initialize sd variable

    # 1. Initialize SDCard object
    try:
        # spi = machine.SPI(
        #     2,  # Use SPI(2) for custom (VSPI on many boards)
        #     sck=machine.Pin(12),
        #     mosi=machine.Pin(11),
        #     miso=machine.Pin(13),
        #     baudrate=1_000_000,  # Safe speed for most cards
        # )

        print("Initializing SD card using default FSPI pins...")
        # Default FSPI pins: SCK=12, MOSI=11, MISO=13, CS=10
        cs_pin = machine.Pin(10, machine.Pin.OUT)
        # Initialize SDCard using keyword arguments for SPI pins as per documentation
        sd = machine.SDCard(
            slot=2,  # Specify SPI slot 2
            sck=machine.Pin(12),
            mosi=machine.Pin(11),
            miso=machine.Pin(13),
            cs=cs_pin,
        )  # Use slot=2 with custom pins, removed freq
        print("SDCard object initialized.")

        # Check basic communication *after* initialization is complete
        try:
            card_info = sd.info()
            print(f"SD Card Info: {card_info}")
        except Exception as e:
            print(f"Error calling sd.info(): {e}")
            # We might want to stop here if info fails, but let's try mounting anyway for now
            pass

    except Exception as e:
        print(f"Error initializing SDCard object: {e}")
        sd = None  # Ensure sd is None if init failed

    # 2. Mount the filesystem if SDCard object was created and info check passed (or was skipped)
    if sd:
        try:
            print(f"Attempting to mount SD card at {SD_MOUNT_POINT}...")
            uos.mount(uos.VfsFat(sd), SD_MOUNT_POINT)
            sd_mounted = True
            print(f"SD card mounted successfully at {SD_MOUNT_POINT}")

            # Optional: List contents
            # print(f"SD Card contents: {os.listdir(SD_MOUNT_POINT)}")
        except OSError as e:
            print(f"Failed to mount SD card: {e}")
            if e.args[0] == 1 or e.args[0] == 19:  # Common errors for no card/issue
                print("No SD card detected or error during mount.")
            elif e.args[0] == 16:  # EEXIST - Mount point exists but couldn't mount device
                print(
                    f"Mount point {SD_MOUNT_POINT} exists, but mount failed. Filesystem issue?"
                )
            # Add other specific errno checks if needed
        except Exception as e:
            print(f"An unexpected error occurred during SD card mount: {e}")
    else:
        print("SDCard object not initialized or info check failed, skipping mount.")
    # --- End SD Card Initialization ---
