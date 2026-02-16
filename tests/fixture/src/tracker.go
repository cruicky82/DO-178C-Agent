package main

import (
	"fmt"
	"math"
)

// Haversine computes the great-circle distance between two points.
func Haversine(lat1, lon1, lat2, lon2 float64) float64 {
	const R = 6371.0 // Earth radius in km
	dLat := (lat2 - lat1) * math.Pi / 180.0
	dLon := (lon2 - lon1) * math.Pi / 180.0
	a := math.Sin(dLat/2)*math.Sin(dLat/2) +
		math.Cos(lat1*math.Pi/180.0)*math.Cos(lat2*math.Pi/180.0)*
			math.Sin(dLon/2)*math.Sin(dLon/2)
	c := 2 * math.Atan2(math.Sqrt(a), math.Sqrt(1-a))
	return R * c
}

// ClassifyAltitude categorizes flight altitude.
func ClassifyAltitude(altFt float64) string {
	if altFt < 0 {
		return "INVALID"
	} else if altFt < 400 {
		return "LOW"
	} else if altFt < 1200 {
		return "MEDIUM"
	} else if altFt < 18000 {
		return "HIGH"
	}
	return "VERY_HIGH"
}

// ProcessTracks filters and processes a slice of track data.
func ProcessTracks(tracks []Track, maxAge int) ([]Track, error) {
	if tracks == nil {
		return nil, fmt.Errorf("tracks cannot be nil")
	}
	var result []Track
	for _, t := range tracks {
		if t.Age <= maxAge {
			result = append(result, t)
		}
	}
	return result, nil
}

type Track struct {
	ID   string
	Lat  float64
	Lon  float64
	Age  int
}
