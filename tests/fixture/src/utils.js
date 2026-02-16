/**
 * utils.js — Test fixture for DO-178C pipeline verification.
 * Utility functions with branches and error handling.
 */

function validateInput(data) {
    if (!data) {
        throw new Error("Input is required");
    }
    if (typeof data.value !== 'number') {
        throw new TypeError("Value must be a number");
    }
    if (data.value < 0 || data.value > 1000) {
        return { valid: false, error: "Out of range" };
    }
    return { valid: true, value: data.value };
}

function computeDistance(lat1, lon1, lat2, lon2) {
    const R = 6371; // km
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

const processItems = (items) => {
    const results = [];
    for (const item of items) {
        if (item.active) {
            try {
                results.push(item.transform());
            } catch (e) {
                console.error(`Failed to process item: ${e.message}`);
            }
        }
    }
    return results;
};

module.exports = { validateInput, computeDistance, processItems };
