let map, marker;
const form = document.getElementById('absenForm');
const button = document.getElementById('absenButton');

function initMap(position) {
    const coords = {
        lat: position.coords.latitude,
        lng: position.coords.longitude
    };

    map = new google.maps.Map(document.getElementById('map'), {
        zoom: 17,
        center: coords,
    });

    marker = new google.maps.Marker({
        position: coords,
        map: map,
    });
}

if (navigator.geolocation) {
    navigator.geolocation.watchPosition(
        (position) => {
            const { latitude, longitude, accuracy } = position.coords;
            
            document.getElementById('coordinates').textContent = 
                `Lokasi: ${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
            document.getElementById('accuracy').textContent = 
                `Akurasi: ±${Math.round(accuracy)} meter`;

            document.getElementById('latitude').value = latitude;
            document.getElementById('longitude').value = longitude;
            document.getElementById('mockLocation').value = position.coords.mocked || false;
            document.getElementById('developerMode').value = 
                /debugger|android\.developer/i.test(navigator.userAgent);

            if (!map) initMap(position);
            else marker.setPosition({ lat: latitude, lng: longitude });

            button.disabled = false;
        },
        (error) => {
            alert('Error: ' + error.message);
            button.disabled = true;
        },
        {
            enableHighAccuracy: true,
            maximumAge: 30000,
            timeout: 27000
        }
    );
} else {
    alert('Geolocation tidak didukung di browser ini');
    button.disabled = true;
} 