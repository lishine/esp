#ifndef I2C_HANDLER_H
#define I2C_HANDLER_H

#include "globals.h"

// --- Function Declarations ---

/**
 * @brief Initializes the I2C peripheral in Slave mode.
 * Sets the slave address and registers the request handler.
 */
void init_i2c_slave();

/**
 * @brief I2C request event handler (ISR context).
 * Called by the Wire library when the I2C Master requests data.
 * Reads the latest averaged RMS value and sends it (2 bytes, little endian).
 */
void i2cRequestEvent();


#endif // I2C_HANDLER_H