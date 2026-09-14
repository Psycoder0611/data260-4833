// Part II - JavaScript
// HW2 - I am extending my HW1 JavaScript and connecting it to FastAPI.


// Base API URL for my Clinical Trial Listings backend
const API_URL = "/api/trials";


// ---------------------------------------------------------
// Page elements
// ---------------------------------------------------------

// I am storing references to the HTML elements that I use multiple times.

const trialForm =
    document.getElementById("clinicalTrialForm");

const trialList =
    document.getElementById("trialList");

const loadingState =
    document.getElementById("loadingState");

const emptyState =
    document.getElementById("emptyState");

const errorState =
    document.getElementById("errorState");

const searchInput =
    document.getElementById("searchInput");

const searchButton =
    document.getElementById("searchButton");

const updateTitle =
    document.getElementById("updateTitle");

const updateSponsor =
    document.getElementById("updateSponsor");

const updateButton =
    document.getElementById("updateButton");

const deleteHighestButton =
    document.getElementById("deleteHighestButton");


// ---------------------------------------------------------
// HW1 validation logic
// ---------------------------------------------------------

// 1a) Arrow func to validate description field
// document.getElementById("description") finds the HTML element with id="description"
// .value gets the text entered by the user
// .trim() removes extra spaces from the beginning & end

const validateForm = () => {

    const description =
        document.getElementById("description").value.trim();

    // Check if the description contains more than 25 characters
    if (description.length <= 25) {

        alert(
            "Trial description must be more than 25 characters."
        );

        return false;
    }


    // 1b) Check whether the terms and conditions checkbox is selected
    // .checked returns true if selected, false if not selected

    const termsChecked =
        document.getElementById("terms").checked;

    if (!termsChecked) {

        alert(
            "Please agree to the terms and conditions."
        );

        return false;
    }


    // If both validations pass, return true
    return true;
};


// ---------------------------------------------------------
// HW1 closure
// ---------------------------------------------------------

// 5) Closure to track successful submissions
// It is put here intentionally outside the event listener.
// A closure allows the inner function to remember
// the count variable even after the outer function finishes.

const submissionCounter = (() => {

    // This variable is private to the closure
    let count = 0;

    // Return an inner function that increases the count
    return () => {

        count++;

        return count;
    };

})();


// ---------------------------------------------------------
// Loading, empty and error states
// ---------------------------------------------------------

// I am hiding all three states first so that only
// the correct state is visible at one time.

function hideAllStates() {

    loadingState.classList.add("hidden");

    emptyState.classList.add("hidden");

    errorState.classList.add("hidden");
}


function showLoadingState() {

    hideAllStates();

    loadingState.classList.remove("hidden");
}


function showEmptyState() {

    hideAllStates();

    emptyState.classList.remove("hidden");
}


function showErrorState() {

    hideAllStates();

    errorState.classList.remove("hidden");
}


// ---------------------------------------------------------
// Display clinical trial records
// ---------------------------------------------------------

function displayTrials(trials) {

    // I am clearing the previous list before displaying
    // the latest records returned by FastAPI.

    trialList.innerHTML = "";

    hideAllStates();


    // If no records are returned, I show the empty state.
    if (trials.length === 0) {

        showEmptyState();

        return;
    }


    // I am creating one card for every clinical trial record.
    trials.forEach((trial) => {

        const trialItem =
            document.createElement("div");

        trialItem.className = "trial-item";


        trialItem.innerHTML = `
            <h3>${trial.trialTitle}</h3>

            <p>
                <strong>ID:</strong>
                ${trial.id}
            </p>

            <p>
                <strong>Sponsor / Institution:</strong>
                ${trial.sponsor}
            </p>

            <p>
                <strong>Study Type:</strong>
                ${trial.category}
            </p>

            <p>
                <strong>Description:</strong>
                ${trial.description}
            </p>

            <p>
                <strong>Submitter Email:</strong>
                ${trial.submitterEmail}
            </p>
        `;


        trialList.appendChild(trialItem);
    });
}


// ---------------------------------------------------------
// READ records + SEARCH
// HW2 Part 2, Question 4
// ---------------------------------------------------------

async function loadTrials(searchValue = "") {

    // I am showing the loading state while waiting
    // for the FastAPI response.

    showLoadingState();

    trialList.innerHTML = "";


    try {

        let url = API_URL;


        // If the user entered a search term,
        // I am sending it to FastAPI using ?q=
        if (searchValue.trim()) {

            const encodedSearch =
                encodeURIComponent(
                    searchValue.trim()
                );

            url =
                `${API_URL}?q=${encodedSearch}`;
        }


        const response =
            await fetch(url);


        if (!response.ok) {

            throw new Error(
                "Unable to retrieve clinical trials."
            );
        }


        const trials =
            await response.json();


        displayTrials(trials);


    } catch (error) {

        console.error(
            "Error loading clinical trials:",
            error
        );


        trialList.innerHTML = "";

        showErrorState();
    }
}


// ---------------------------------------------------------
// CREATE RECORD
// HW2 Part 2, Question 1
// ---------------------------------------------------------

// Form submission event, supporting code used to run HW1 questions
// and now extended in HW2 to send the data to FastAPI.

// Adding an event listener to the form.
// This listens for the "submit" event when the user clicks the submit button.

trialForm.addEventListener(
    "submit",
    async (event) => {

        // Prevent the form from refreshing or reloading immediately
        event.preventDefault();


        // Call our validation function.
        // If validation fails, stop here.
        if (!validateForm()) {

            return;
        }


        // If validation passes, continue here
        console.log(
            "Form validation successful."
        );


        // -------------------------------------------------
        // 2) Convert successful form data to JSON
        // -------------------------------------------------

        // Collect data entered in the form

        const trialTitle =
            document.getElementById("trialTitle").value.trim();

        const sponsor =
            document.getElementById("sponsor").value.trim();

        const submitterEmail =
            document.getElementById("submitterEmail").value.trim();

        const description =
            document.getElementById("description").value.trim();

        const category =
            document.getElementById("category").value;

        const termsAccepted =
            document.getElementById("terms").checked;


        // Create a JavaScript object containing all form data.
        // I am keeping termsAccepted here for my HW1 demonstration.

        const trialDataForHW1 = {

            trialTitle,
            sponsor,
            submitterEmail,
            description,
            category,
            termsAccepted
        };


        // Convert the JavaScript object into a JSON string.
        // JSON.stringify() converts an object into JSON text.

        const jsonString =
            JSON.stringify(
                trialDataForHW1
            );


        // Log the JSON string in the browser console.

        console.log(
            "Clinical Trial Data (JSON String):",
            jsonString
        );


        // -------------------------------------------------
        // 3) Object destructuring
        // -------------------------------------------------

        // Convert the JSON string back into a JavaScript object.
        // JSON.parse() changes JSON text back into an object.

        const parsedTrialData =
            JSON.parse(jsonString);


        // Rename the destructured values to avoid redeclaring variables
        // that were already declared earlier with const.

        const {
            trialTitle: parsedTrialTitle,
            submitterEmail: parsedSubmitterEmail
        } = parsedTrialData;


        console.log(
            "Trial Title:",
            parsedTrialTitle
        );


        console.log(
            "Submitter Email:",
            parsedSubmitterEmail
        );


        // -------------------------------------------------
        // 4) Spread operator + submissionDate
        // -------------------------------------------------

        // The spread operator (...) copies all fields
        // from parsedTrialData into a new object.

        const updatedTrialData = {

            ...parsedTrialData,

            // Add a new field with the current date and time
            submissionDate:
                new Date().toISOString()
        };


        // Log the updated object in the console

        console.log(
            "Updated Clinical Trial Data:",
            updatedTrialData
        );


        // -------------------------------------------------
        // HW2 - Send the record to FastAPI
        // -------------------------------------------------

        // FastAPI only needs the actual clinical trial fields.
        // I am not sending termsAccepted or submissionDate
        // because they are not part of the backend model.

        const apiTrialData = {

            trialTitle,
            sponsor,
            submitterEmail,
            description,
            category
        };


        try {

            const response =
                await fetch(
                    API_URL,
                    {
                        method: "POST",

                        headers: {
                            "Content-Type":
                                "application/json"
                        },

                        body:
                            JSON.stringify(
                                apiTrialData
                            )
                    }
                );


            if (!response.ok) {

                const errorData =
                    await response.json();


                throw new Error(
                    errorData.detail ||
                    "Unable to create clinical trial."
                );
            }


            const newTrial =
                await response.json();


            console.log(
                "Created clinical trial:",
                newTrial
            );


            // -------------------------------------------------
            // 5) Log successful submission count
            // -------------------------------------------------

            const currentSubmissionCount =
                submissionCounter();


            console.log(
                "Successful Submission Count:",
                currentSubmissionCount
            );


            // I am clearing the form after the record is added.
            trialForm.reset();


            // I am loading the records again so the new record
            // appears immediately in the home view.
            await loadTrials();


            alert(
                `Clinical trial "${newTrial.trialTitle}" added successfully.`
            );


        } catch (error) {

            console.error(
                "Error creating clinical trial:",
                error
            );


            alert(
                "Unable to add clinical trial: " +
                error.message
            );
        }
    }
);


// ---------------------------------------------------------
// UPDATE RECORD ID 1
// HW2 Part 2, Question 2
// ---------------------------------------------------------

updateButton.addEventListener(
    "click",
    async () => {

        const newTitle =
            updateTitle.value.trim();

        const newSponsor =
            updateSponsor.value.trim();


        // Both fields are required because HW2 specifically asks
        // me to update the primary and secondary fields.

        if (!newTitle || !newSponsor) {

            alert(
                "Please enter both the updated title and sponsor."
            );

            return;
        }


        try {

            // I am updating record ID 1 specifically
            // because HW2 requires record ID 1 to be updated.

            const response =
                await fetch(
                    `${API_URL}/1`,
                    {
                        method: "PUT",

                        headers: {
                            "Content-Type":
                                "application/json"
                        },

                        body:
                            JSON.stringify({
                                trialTitle: newTitle,
                                sponsor: newSponsor
                            })
                    }
                );


            if (!response.ok) {

                const errorData =
                    await response.json();


                throw new Error(
                    errorData.detail ||
                    "Unable to update clinical trial."
                );
            }


            const updatedTrial =
                await response.json();


            console.log(
                "Updated clinical trial:",
                updatedTrial
            );


            // I am clearing the update fields after success.
            updateTitle.value = "";
            updateSponsor.value = "";


            // I am reloading the home list so the updated
            // title and sponsor are immediately visible.
            await loadTrials();


            alert(
                "Clinical trial ID 1 updated successfully."
            );


        } catch (error) {

            console.error(
                "Error updating clinical trial:",
                error
            );


            alert(
                "Unable to update clinical trial: " +
                error.message
            );
        }
    }
);


// ---------------------------------------------------------
// DELETE RECORD WITH HIGHEST ID
// HW2 Part 2, Question 3
// ---------------------------------------------------------

deleteHighestButton.addEventListener(
    "click",
    async () => {

        try {

            // I first retrieve all current records because
            // I need to find which record has the highest ID.

            const response =
                await fetch(API_URL);


            if (!response.ok) {

                throw new Error(
                    "Unable to retrieve clinical trials."
                );
            }


            const trials =
                await response.json();


            // If there are no records, there is nothing to delete.
            if (trials.length === 0) {

                alert(
                    "There are no clinical trial records to delete."
                );

                return;
            }


            // I am getting all IDs and finding the largest one.
            const highestId =
                Math.max(
                    ...trials.map(
                        (trial) => trial.id
                    )
                );


            // I am asking for confirmation before deleting the record.
            const confirmed =
                confirm(
                    `Delete the clinical trial with highest ID ${highestId}?`
                );


            if (!confirmed) {

                return;
            }


            // I am sending the highest ID to my FastAPI
            // DELETE endpoint.

            const deleteResponse =
                await fetch(
                    `${API_URL}/${highestId}`,
                    {
                        method: "DELETE"
                    }
                );


            if (!deleteResponse.ok) {

                throw new Error(
                    "Unable to delete clinical trial."
                );
            }


            console.log(
                `Deleted clinical trial ID ${highestId}`
            );


            // I reload the list so the deleted record
            // disappears from the home view.

            await loadTrials();


            alert(
                `Clinical trial ID ${highestId} deleted successfully.`
            );


        } catch (error) {

            console.error(
                "Error deleting clinical trial:",
                error
            );


            alert(
                "Unable to delete clinical trial: " +
                error.message
            );
        }
    }
);


// ---------------------------------------------------------
// SEARCH
// HW2 Part 2, Question 4
// ---------------------------------------------------------

// I am searching by the primary field (trial title)
// or secondary field (sponsor/institution).

searchButton.addEventListener(
    "click",
    () => {

        loadTrials(
            searchInput.value
        );
    }
);


// I am also allowing the Enter key to start the search.

searchInput.addEventListener(
    "keydown",
    (event) => {

        if (event.key === "Enter") {

            event.preventDefault();


            loadTrials(
                searchInput.value
            );
        }
    }
);


// ---------------------------------------------------------
// Initial page load
// ---------------------------------------------------------

// I am loading the existing records automatically
// when the page first opens.

document.addEventListener(
    "DOMContentLoaded",
    () => {

        loadTrials();
    }
);