use esp_idf_hal::gpio::PinDriver;
use esp_idf_hal::delay::FreeRtos;
use esp_idf_hal::peripherals::Peripherals;

fn main() {
    // Initialize ESP-IDF
    esp_idf_svc::sys::link_patches();
    esp_idf_svc::log::EspLogger::initialize_default();

    // Configure watchdog with longer timeout or disable it
    unsafe {
        let config = esp_idf_svc::sys::esp_task_wdt_config_t {
            timeout_ms: 10000,        // 10 second timeout
            idle_core_mask: (1 << 0), // Monitor core 0's idle task
            trigger_panic: true,      // Trigger panic on timeout
        };
        let result = esp_idf_svc::sys::esp_task_wdt_init(&config);
        if result != 0 {
            log::warn!("Failed to initialize watchdog timer: {}", result);
        }
    }


    let peripherals = Peripherals::take().unwrap();
    let mut led = PinDriver::output(peripherals.pins.gpio8).unwrap();

    log::info!("Flashing LED on pin 8");
    loop {
        if let Err(e) = led.set_high() {
            log::error!("Failed to set LED high: {:?}", e);
        }
        FreeRtos::delay_ms(500); // Use FreeRtos delay which handles watchdog timers
        
        if let Err(e) = led.set_low() {
            log::error!("Failed to set LED low: {:?}", e);
        }
        log::info!("Hehhhhhhhhhhllo, world!");
        FreeRtos::delay_ms(800); // Use FreeRtos delay which handles watchdog timers
    }
}