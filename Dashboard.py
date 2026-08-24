<!DOCTYPE html>
<html>
<head>
    <title>Admin Dashboard</title>
    <!-- Flatpickr CSS & JS (تاریخ کو بہتر انداز میں دکھانے کے لیے) -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
    <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
    
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; }
        .dashboard-container { display: flex; gap: 20px; margin-bottom: 30px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 20px; }
        .stat-card { border: 1px solid #ddd; padding: 10px; border-radius: 8px; text-align: center; background: #f4f4f4; }
        .btn { padding: 8px 15px; background-color: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
        .btn-green { background-color: #28a745; }
        .btn-orange { background-color: #fd7e14; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        .profile-img { width: 50px; height: 50px; border-radius: 50%; object-fit: cover; }
    </style>
</head>
<body>

    <h1>Welcome, {{ username }}!</h1>

    <div class="stats-grid">
        <div class="stat-card"><small>Total Users</small><h4>{{ total_users }}</h4></div>
        <div class="stat-card"><small>Total Coins</small><h4>{{ total_coins }}</h4></div>
        <div class="stat-card"><small>Total Bonus</small><h4>{{ total_bonus }}</h4></div>
        <div class="stat-card"><small>Total Withdraw</small><h4>{{ total_withdraw }}</h4></div>
        <div class="stat-card"><small>Total Deposit</small><h4>{{ total_deposit }}</h4></div>
        <div class="stat-card"><small>COINS RATE</small><h4>{{ coin_rate|default('0.0000') }}</h4></div>
    </div>

    <!-- Coin Rate Trend Graph -->
    <div style="background: #1e1e1e; padding: 15px; border-radius: 8px; margin: 15px 0; border: 1px solid #333;">
        <h4 style="color: #fff; margin-bottom: 10px; font-size: 14px;"><i class="fas fa-chart-line"></i> Coin Rate Trend</h4>
        <canvas id="coinRateChart" width="400" height="100"></canvas>
    </div>

    <!-- Chart.js Script -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
    const ctx = document.getElementById('coinRateChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: {{ timestamps | safe }},
            datasets: [{
                label: 'Coin Rate',
                data: {{ rates | safe }},
                borderColor: '#00cec9',
                backgroundColor: 'rgba(0, 206, 201, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: { ticks: { color: '#aaa', font: { size: 10 } }, grid: { color: '#333' } },
                y: { ticks: { color: '#aaa', font: { size: 10 } }, grid: { color: '#333' } }
            },
            plugins: { legend: { display: false } }
        }
    });
    </script>

    <!-- ودڈرا ریکویسٹس -->
    <h2>Pending Withdrawals</h2>
    <table>
        <tr>
            <th>User</th>
            <th>Amount</th>
            <th>Action</th>
        </tr>
        {% for req in withdrawals %}
        <tr>
            <td>{{ req.username }}</td>
            <td>{{ req.amount }}</td>
            <td>
                <a href="/approve_withdraw/{{ req.id }}" class="btn btn-green">Approve</a>
            </td>
        </tr>
        {% endfor %}
    </table>

    <hr>

    <!-- یوزرز لسٹ -->
    <h2>All Users</h2>
    <table>
        <tr>
            <th>Profile</th> <th>User ID</th>
            <th>Username</th>
            <th>Coins</th>
            <th>Action</th>
        </tr>
        {% for user in users %}
        <tr>
            <td>
                {% if user.profile_pic %}
                    <img src="{{ url_for('static', filename='uploads/' + user.profile_pic) }}" class="profile-img">
                {% else %}
                    <span>No Pic</span>
                {% endif %}
            </td>
            <td>{{ user.id }}</td>
            <td>{{ user.username }}</td>
            <td><span id="coin-val-{{ user.id }}">{{ user.coins }}</span></td>
            <td>
                <input type="number" id="input-{{ user.id }}" style="width: 60px;" placeholder="Value">
                <button onclick="updateCoins({{ user.id }}, 'add')">Add</button>
                <button onclick="updateCoins({{ user.id }}, 'less')">Less</button>
            </td>
        </tr>
        {% endfor %}
    </table>

    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script>
    function updateCoins(userId, action) {
        let amount = $('#input-' + userId).val();
        $.ajax({
            url: '/update_coins',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ userId: userId, amount: amount, action: action }),
            success: function(response) {
                alert("کامیاب!");
                location.reload();
            }
        });
    }
    </script>
</body>
</html>