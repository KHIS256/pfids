// This event listener ensures that the code runs only after the entire HTML
// document has been loaded and parsed.
document.addEventListener('DOMContentLoaded', () => {
    const listContainer = document.getElementById('flight-list-container');
    const departuresBtn = document.getElementById('departures-btn');
    const arrivalsBtn = document.getElementById('arrivals-btn');
    const searchInput = document.getElementById('search-input');
    const colLocation = document.getElementById('col-location');
    const colSecondaryLocation = document.getElementById('col-secondary-location');
    const statusIndicator = document.getElementById('status-indicator');
    const sortableHeaders = document.querySelectorAll('.sortable-header');
    
    let allFlights = [];
    let currentFlights = [];
    let currentMode = 'departures';
    let fetchAttempts = 0;
    let sortState = { key: 'time', direction: 'asc' };

    function updateStatusIndicator(status, message) {
        statusIndicator.className = `status-indicator ${status}`;
        statusIndicator.textContent = message;
    }

    function renderFlights(flightsToRender) {
        listContainer.innerHTML = '';
        
        if (flightsToRender.length === 0) {
            let messageText = 'No flights match your search.';
            if (searchInput.value === '') {
                messageText = 'No flight data available.';
            }
            listContainer.innerHTML = `<div class="message">${messageText}</div>`;
            return;
        }

        const isMobile = window.innerWidth <= 1024;
        const locationLabel = currentMode === 'departures' ? 'Destination' : 'Origin';
        const secondaryLocationLabel = currentMode === 'departures' ? 'Check-in' : 'Baggage';

        flightsToRender.forEach(flight => {
            const row = document.createElement('div');
            const statusClass = flight.status ? flight.status.toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]/g, '') : 'default';
            const flightNumbersHtml = flight.flight_numbers_only ? flight.flight_numbers_only.map(fn => `<div class="flight-number">${fn}</div>`).join('') : '<div class="flight-number">N/A</div>';

            if (isMobile) {
                row.className = 'flight-row-mobile';
                row.innerHTML = `
                    <div class="mobile-grid-item time-item">
                        <div class="label">Time</div>
                        <div class="value flight-time">${flight.time || '-'}</div>
                    </div>
                    <div class="mobile-grid-item flight-item">
                        <div class="label">Flight</div>
                        <div class="value flight-numbers">${flightNumbersHtml}</div>
                    </div>
                    <div class="mobile-grid-item destination-item">
                        <div class="label">${locationLabel}</div>
                        <div class="value flight-location">${flight.location || '-'}</div>
                    </div>
                    <div class="mobile-grid-item terminal-item">
                        <div class="label">Terminal</div>
                        <div class="value detail-value">${flight.terminal || '-'}</div>
                    </div>
                    <div class="mobile-grid-item checkin-item">
                        <div class="label">${secondaryLocationLabel}</div>
                        <div class="value detail-value">${flight.location_secondary || '-'}</div>
                    </div>
                    <div class="mobile-grid-item gate-item">
                        <div class="label">Gate</div>
                        <div class="value detail-value">${flight.gate || '-'}</div>
                    </div>
                    <div class="mobile-grid-item status-item">
                        <div class="label">Status</div>
                        <div class="value"><span class="status ${statusClass}">${flight.status || '-'}</span></div>
                    </div>
                `;
            } else {
                row.className = 'flight-row-desktop';
                row.innerHTML = `
                    <div class="flight-time">${flight.time || '-'}</div>
                    <div class="flight-numbers">${flightNumbersHtml}</div>
                    <div class="flight-location">${flight.location || '-'}</div>
                    <div class="detail-value">${flight.terminal || '-'}</div>
                    <div class="detail-value">${flight.location_secondary || '-'}</div>
                    <div class="detail-value">${flight.gate || '-'}</div>
                    <div><span class="status ${statusClass}">${flight.status || '-'}</span></div>
                `;
            }
            listContainer.appendChild(row);
        });
    }
    
    function filterAndRenderFlights() {
        const searchTerm = searchInput.value.toLowerCase();
        
        if (!searchTerm) {
            currentFlights = [...allFlights];
        } else {
            currentFlights = allFlights.filter(flight => {
                const flightNumMatch = flight.flight_numbers_only.some(fn => fn.toLowerCase().includes(searchTerm));
                const locationMatch = flight.location.toLowerCase().includes(searchTerm);
                const terminalMatch = (flight.terminal || '').toLowerCase().includes(searchTerm);
                const gateMatch = (flight.gate || '').toLowerCase().includes(searchTerm);
                return flightNumMatch || locationMatch || terminalMatch || gateMatch;
            });
        }
        sortAndRenderFlights();
    }

    function sortAndRenderFlights() {
        let processedFlights = [...currentFlights];

        processedFlights.sort((a, b) => {
            const key = sortState.key;
            let valA = a[key] || '';
            let valB = b[key] || '';

            if (key === 'flight_numbers_only') {
                valA = valA[0] || '';
                valB = valB[0] || '';
            }
            
            const isANa = valA === '-' || valA === '';
            const isBNa = valB === '-' || valB === '';
            if (isANa && isBNa) return 0;
            if (isANa) return 1;
            if (isBNa) return -1;

            let comparison = valA.localeCompare(valB, undefined, { numeric: true });
            return sortState.direction === 'asc' ? comparison : -comparison;
        });

        renderFlights(processedFlights);
        updateHeaderStyles();
    }

    function updateHeaderStyles() {
        sortableHeaders.forEach(header => {
            header.classList.remove('sorted-asc', 'sorted-desc');
            if (header.dataset.sortKey === sortState.key) {
                header.classList.add(sortState.direction === 'asc' ? 'sorted-asc' : 'sorted-desc');
            }
        });
    }

    async function fetchAndDisplayData() {
        // IMPORTANT: Remember to replace this placeholder URL with your actual
        // backend URL from Render.com when you deploy.
        const baseUrl = 'http://127.0.0.1:5001'; 
        const url = currentMode === 'departures' ? `${baseUrl}/api/departures` : `${baseUrl}/api/arrivals`;

        fetchAttempts++;
        updateStatusIndicator('loading', 'Loading...');
        
        try {
            const response = await fetch(`${url}?v=${new Date().getTime()}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            
            if (!data.version || data.error) {
                throw new Error(data.error || "Invalid data format.");
            }
            
            allFlights = data.flights || [];
            filterAndRenderFlights();
            
            if (allFlights.length > 0) {
                const now = new Date();
                const hktFormatter = new Intl.DateTimeFormat('en-GB', {
                    timeZone: 'Asia/Hong_Kong',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false
                });
                const hktTime = hktFormatter.format(now);
                updateStatusIndicator('success', `Updated at ${hktTime} (HKT)`);
            } else {
                updateStatusIndicator('warning', 'No flights');
            }
        } catch (error) {
            console.error("Fetch error:", error);
            allFlights = [];
            currentFlights = [];
            updateStatusIndicator('error', 'Error');
            renderFlights([]);
        }
    }

    function switchMode(newMode) {
        if (newMode === currentMode && fetchAttempts > 0) return;
        currentMode = newMode;
        
        departuresBtn.classList.toggle('active', newMode === 'departures');
        arrivalsBtn.classList.toggle('active', newMode === 'arrivals');
        
        const locationHeader = colLocation.querySelector('span');
        const secondaryHeader = colSecondaryLocation.querySelector('span');
        if (newMode === 'departures') {
            locationHeader.textContent = 'Destination';
            secondaryHeader.textContent = 'Check-in';
        } else {
            locationHeader.textContent = 'Origin';
            secondaryHeader.textContent = 'Baggage';
        }
        
        fetchAttempts = 0;
        fetchAndDisplayData();
    }

    sortableHeaders.forEach(header => {
        header.addEventListener('click', () => {
            const newSortKey = header.dataset.sortKey;
            if (sortState.key === newSortKey) {
                sortState.direction = sortState.direction === 'asc' ? 'desc' : 'asc';
            } else {
                sortState.key = newSortKey;
                sortState.direction = 'asc';
            }
            sortAndRenderFlights();
        });
    });

    departuresBtn.addEventListener('click', () => switchMode('departures'));
    arrivalsBtn.addEventListener('click', () => switchMode('arrivals'));
    searchInput.addEventListener('input', filterAndRenderFlights);
    
    window.addEventListener('resize', () => renderFlights(currentFlights));

    // Initial setup
    switchMode('departures');
    setInterval(fetchAndDisplayData, 60000);
});