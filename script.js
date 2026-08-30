// Part II - Javascript

// 1a) Arrow func to validate description field
// document.getElementById("description") finds the HTML element with id="description"
// .value gets the text entered by the user
// .trim() removes extra spaces from the beginning & end

const validateForm = () => {
    const description = document.getElementById("description").value.trim();

    // Check if the description contains more than 25 characters
    if (description.length <= 25) {
        alert("Trial description must be more than 25 characters.");
        return false;
    }

// 1b) Check whether the terms and conditions checkbox is selected
// .checked returns true if selected, false if not selected
    const termsChecked = document.getElementById("terms").checked;

    if (!termsChecked) {
        alert("Please agree to the terms and conditions.");
        return false;
    }

    // If both validations pass, return true
    return true;
};

// 5) Closure to track successful submissions   -- it is put here intentinally outside the event listener
    // A closure allows the inner func to remember
    // the count variable even after the outer func finishes
    const submissionCounter = (() => {

        // This variable is private to the closure
        let count = 0;
    
        // Return an inner function that increases the count
        return () => {
            count++;
            return count;
        };
    
    })();

// Form submission event, Supporting code used to run Questions 1-5
// Adding an event listener to the form
// This listens for the "submit" event when the user clicks the submit button

document.getElementById("clinicalTrialForm").addEventListener("submit", (event) => {

    // Prevent the form from refreshing or reloading immediately
    event.preventDefault();

    // Call our validation function
    // If validation fails, stop here
    if (!validateForm()) {
        return;
    }

    // If validation passes, continue here
    console.log("Form validation successful.");

// 2) Convert successful form data to JSON
// Collect data entered in the form

    const trialTitle = document.getElementById("trialTitle").value.trim();
    const sponsor = document.getElementById("sponsor").value.trim();
    const submitterEmail = document.getElementById("submitterEmail").value.trim();
    const description = document.getElementById("description").value.trim();
    const category = document.getElementById("category").value;
    const termsAccepted = document.getElementById("terms").checked;


    // Create a JavaScript object containing all form data

    const trialData = {
        trialTitle,
        sponsor,
        submitterEmail,
        description,
        category,
        termsAccepted
    };


    // Convert the JavaScript object into a JSON string
    // JSON.stringify() converts an object into JSON text

    const jsonString = JSON.stringify(trialData);


    // Log the JSON string in the browser console

    console.log("Clinical Trial Data (JSON String):", jsonString);


// 3. Object destructuring
    // Convert the JSON string back into a JavaScript object
    // JSON.parse() changes JSON text back into an object
    const parsedTrialData = JSON.parse(jsonString);

    // Rename the destructured values to avoid redeclaring variables, already declared trialTitle & submitterEmail earlier in Question 2 with const
    const {
        trialTitle: parsedTrialTitle,
        submitterEmail: parsedSubmitterEmail
    } = parsedTrialData;

    console.log("Trial Title:", parsedTrialTitle);
    console.log("Submitter Email:", parsedSubmitterEmail);


// 4) Spread operator + submissionDate

    // The spread operator (...) copies all fields
    // from parsedTrialData into a new object
    const updatedTrialData = {
        ...parsedTrialData,

        // Add a new field with the current date and time
        submissionDate: new Date().toISOString()
    };

    // Log the updated object in the console
    console.log("Updated Clinical Trial Data:", updatedTrialData);

    
// 5) Log successful submission count
   
    const currentSubmissionCount = submissionCounter();
    console.log("Successful Submission Count:", currentSubmissionCount);

});

