const express = require("express");
const { Pool } = require("pg");
const cors = require("cors");
const app = express();

// connect to database 
const pool = new Pool({
    user : 'postgres' , 
    host : 'localhost' , 
    database : 'UberDB' , // نام دیتابیس طبق تصویر شما
    password : '4043614002' , 
    port : 5432
})

app.use(cors());
app.use(express.json());

// read trips 
app.get("/trips", async (req, res) => {
  try {
    const { customer_id } = req.query;
    let query = "SELECT * FROM gold.dataset";
    let params = [];

    if (customer_id) {
      query += " WHERE customer_id = $1";
      params.push(customer_id);
    }
    
    // 50 trips for high speed 
    query += " ORDER BY trip_id DESC LIMIT 50";

    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch (err) {
    console.error(err.message);
    res.status(500).send("Server Error");
  }
});

// بخشی از فایل server/index.js
app.post("/trips", async (req, res) => {
  try {
    const { date, time, vehicle_type, payment_method, customer_rating } = req.body;

    // 1. محاسبه دستی روز و ساعت
    const d = new Date(date);
    const days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
    const my_day = days[d.getDay()]; // محاسبه نام روز
    const my_hour = parseInt(time.split(":")[0]); // محاسبه ساعت

    const booking_id = "NEW" + Math.floor(Math.random() * 100000);

    // 2. ارسال به دیتابیس (دقت کنید که $7 و $8 اضافه شده‌اند)
    const newTrip = await pool.query(
      `INSERT INTO gold.dataset (
         booking_id, date, time, vehicle_type, payment_method, customer_rating, booking_status, 
         day_name, hour
       ) 
       VALUES ($1, $2, $3, $4, $5, $6, 'Completed', $7, $8) RETURNING *`,
      [booking_id, date, time, vehicle_type, payment_method, customer_rating, my_day, my_hour]
    );

    res.json(newTrip.rows[0]);
  } catch (err) {
    console.error(err.message);
    res.status(500).send(err.message);
  }
});
// edit trip or state of the trip
app.put("/trips/:id", async (req, res) => {
  try {
    const { id } = req.params;
    const { vehicle_type, booking_status } = req.body;
    
    const updateTrip = await pool.query(
      "UPDATE gold.dataset SET vehicle_type = $1, booking_status = $2 WHERE trip_id = $3 RETURNING *",
      [vehicle_type, booking_status, id]
    );

    res.json("Trip updated!");
  } catch (err) {
    console.error(err.message);
  }
});

// delete trip
app.delete("/trips/:id", async (req, res) => {
  try {
    const { id } = req.params;
    await pool.query("DELETE FROM gold.dataset WHERE trip_id = $1", [id]);
    res.json("Trip deleted!");
  } catch (err) {
    console.error(err.message);
  }
});

app.listen(5000, () => {
  console.log("Server is starting on port 5000");
});