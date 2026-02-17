import { useState, useEffect } from "react";
import axios from "axios";
import "./App.css";

function App() {
  const [trips, setTrips] = useState([]);
  const [filterId, setFilterId] = useState("");
  
  // متغیرهای ویرایش
  const [editId, setEditId] = useState(null); 
  const [editStatus, setEditStatus] = useState(""); 
  
  const STATUS_OPTIONS = ["Completed", "Cancelled by Driver", "Cancelled by Customer", "Incomplete"];

  const [formData, setFormData] = useState({
    date: "2026-01-08",
    time: "12:00:00",
    vehicle_type: "Auto",
    payment_method: "Cash",
    customer_rating: 5,
  });

  // دریافت داده‌ها
  const fetchTrips = async () => {
    try {
      const url = filterId 
        ? `http://localhost:5000/trips?customer_id=${filterId}` 
        : "http://localhost:5000/trips";
      const response = await axios.get(url);
      setTrips(response.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchTrips();
  }, [filterId]);

  // ثبت داده
  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post("http://localhost:5000/trips", formData);
      alert("New trip created!");
      fetchTrips();
    } catch (err) {
      console.error(err);
    }
  };

  // حذف داده
  const handleDelete = async (id) => {
    if (window.confirm("Are you sure?")) {
      try {
        await axios.delete(`http://localhost:5000/trips/${id}`);
        fetchTrips();
      } catch (err) {
        console.error(err);
      }
    }
  };

  // شروع ویرایش
  const startEditing = (trip) => {
    setEditId(trip.trip_id);       
    setEditStatus(trip.booking_status); 
  };

  // ذخیره ویرایش
  const saveUpdate = async (trip) => {
    try {
      await axios.put(`http://localhost:5000/trips/${trip.trip_id}`, {
        vehicle_type: trip.vehicle_type,
        booking_status: editStatus, 
      });
      setEditId(null); 
      fetchTrips();    
      alert("Status Updated!");
    } catch (err) {
      console.error("Error:", err);
    }
  };

  const cancelEdit = () => setEditId(null);

  // --- طراحی صفحه ---
  return (
    <div style={{ padding: "20px", fontFamily: "Arial" }}>
      
      {/* --- دکمه اتصال به داشبورد Streamlit (جدید) --- */}
      <div style={{ 
        display: "flex", justifyContent: "space-between", alignItems: "center",
        background: "#2c3e50", color: "white", padding: "15px", borderRadius: "8px", marginBottom: "20px"
      }}>
        <h1 style={{ margin: 0, fontSize: "24px" }}>🚖 Uber Admin Panel</h1>
        
        <button 
          onClick={() => window.open('http://localhost:8501', '_blank')}
          style={{ 
            backgroundColor: "#e74c3c", color: "white", padding: "10px 20px", 
            fontSize: "16px", fontWeight: "bold", border: "none", borderRadius: "5px", cursor: "pointer"
          }}
        >
          📊 Go to Analytics Dashboard
        </button>
      </div>

      {/* بخش جستجو */}
      <div style={{ marginBottom: "20px", padding: "15px", border: "1px solid #ddd", borderRadius: "8px" }}>
        <h3>🔍 Filter by Customer ID</h3>
        <input
          placeholder="Enter Customer ID..."
          value={filterId}
          onChange={(e) => setFilterId(e.target.value)}
          style={{ padding: "8px", width: "200px" }}
        />
      </div>

      {/* بخش فرم ثبت */}
      <div style={{ marginBottom: "20px", padding: "15px", border: "1px solid #ddd", borderRadius: "8px", background: "#f9f9f9" }}>
        
        <form onSubmit={handleSubmit} style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
          <input type="date" value={formData.date} onChange={e => setFormData({...formData, date: e.target.value})} required style={{padding: "8px"}} />
          <input type="time" step="1" value={formData.time} onChange={e => setFormData({...formData, time: e.target.value})} required style={{padding: "8px"}} />
          
          <select value={formData.vehicle_type} onChange={e => setFormData({...formData, vehicle_type: e.target.value})} style={{ padding: "8px" }}>
            <option value="Auto">Auto</option>
            <option value="Bike">Bike</option>
            <option value="Car">Car</option>
          </select>

          <select value={formData.payment_method} onChange={e => setFormData({...formData, payment_method: e.target.value})} style={{ padding: "8px" }}>
            <option value="Cash">Cash</option>
            <option value="Credit Card">Credit Card</option>
            <option value="UPI">UPI</option>
            <option value="Wallet">Wallet</option>
          </select>

          <input type="number" min="0" max="5" step="0.1" placeholder="Rating" value={formData.customer_rating} onChange={e => setFormData({...formData, customer_rating: e.target.value})} style={{ width: "80px", padding: "8px" }} required />

          <button type="submit" style={{ background: "#27ae60", color: "white", padding: "8px 20px", border: "none", borderRadius: "4px", cursor: "pointer" }}>Create</button>
        </form>
      </div>

      {/* جدول نمایش داده‌ها */}
      <table border="1" cellPadding="10" style={{ width: "100%", borderCollapse: "collapse", boxShadow: "0 0 10px rgba(0,0,0,0.1)" }}>
        <thead>
          <tr style={{ background: "#ecf0f1", color: "#2c3e50" }}>
            <th>Trip ID</th>
            <th>Date</th>
            <th>Day</th>
            <th>Time</th>
            <th>Hour</th>
            <th>Vehicle</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {trips.map((trip) => (
            <tr key={trip.trip_id} style={{ textAlign: "center" }}>
              <td>{trip.trip_id}</td>
              <td>{trip.date ? trip.date.split('T')[0] : ''}</td>
              <td style={{ color: "white", fontWeight: "bold" }}>{trip.day_name}</td>
              <td>{trip.time}</td>
              <td style={{ color: "white", fontWeight: "bold" }}>{trip.hour}</td>
              <td>{trip.vehicle_type}</td>
              
              <td>
                {editId === trip.trip_id ? (
                  <select value={editStatus} onChange={(e) => setEditStatus(e.target.value)} style={{ padding: "5px" }}>
                    {STATUS_OPTIONS.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                  </select>
                ) : (
                  <span style={{ 
                    padding: "5px 10px", borderRadius: "15px", fontSize: "12px",
                    background: trip.booking_status === 'Completed' ? '#d5f5e3' : '#fadbd8',
                    color: trip.booking_status === 'Completed' ? '#186a3b' : '#943126'
                  }}>
                    {trip.booking_status}
                  </span>
                )}
              </td>

              <td>
                {editId === trip.trip_id ? (
                  <>
                    <button onClick={() => saveUpdate(trip)} style={{ marginRight: "5px", background: "#27ae60", color: "white", border:"none", padding:"5px 10px", cursor:"pointer" }}>Save</button>
                    <button onClick={cancelEdit} style={{ background: "#95a5a6", color: "white", border:"none", padding:"5px 10px", cursor:"pointer" }}>Cancel</button>
                  </>
                ) : (
                  <>
                    <button onClick={() => startEditing(trip)} style={{ marginRight: "5px", background: "#f39c12", color: "white", border:"none", padding:"5px 10px", cursor:"pointer" }}>Update</button>
                    <button onClick={() => handleDelete(trip.trip_id)} style={{ background: "#c0392b", color: "white", border:"none", padding:"5px 10px", cursor:"pointer" }}>Delete</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;